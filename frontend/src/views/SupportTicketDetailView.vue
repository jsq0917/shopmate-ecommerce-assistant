<script setup lang="ts">
/**
 * 工单详情：安全摘要 + 会话解释（消息/引用/工具/风险）+ 接管/解决/关闭。
 * 状态转换由后端校验（docs/06-api.md 第 12 节状态机），前端只提交动作。
 *
 * 权限边界：**读不设限、写必须先接管**。会话取证是判断「要不要接这个工单」的依据，
 * 所以未接管也能看；回复、打分、解决、关闭都会写进这个案例，必须先点「接管」。
 * 后端 `ensure_reply_allowed` / `ensure_ticket_owned` 是硬边界，这里的禁用态只是让
 * 用户在点击前就知道原因，不作为安全边界。
 */

import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElDialog, ElInput, ElMessage, ElMessageBox, ElTag } from 'element-plus'

import QualityLabelForm from '@/components/support/QualityLabelForm.vue'
import SupportConversationPanel from '@/components/support/SupportConversationPanel.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { useAuthStore } from '@/stores/auth'
import { supportApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { SupportConversation, SupportTicketDetail } from '@/api/types'
import { formatDateTime, handoffReasonLabel, riskLevelLabel, ticketStatusLabel } from '@/utils/format'
import {
  hasTakeoverMemory,
  rememberTakeover,
  syncTakeoverMemory,
} from '@/utils/takeoverMemory'

/** 会话轮询间隔：客服在详情页等用户回话，不刷新就等于收不到消息。 */
const CONVERSATION_POLL_MS = 10_000

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const ticketId = String(route.params.ticketId ?? '')
const currentUserId = computed(() => auth.user?.user_id ?? null)

const loading = ref(true)
const error = ref<ApiError | null>(null)
const ticket = ref<SupportTicketDetail | null>(null)
const conversation = ref<SupportConversation | null>(null)
/** 会话取不到时的原因（例如用户已删除会话）；工单本身仍可读，不应整页报错。 */
const transcriptError = ref<string | null>(null)

const actionLoading = ref(false)
const actionError = ref<ApiError | null>(null)
const actionNotice = ref('')

const replyDraft = ref('')
const replySending = ref(false)
/** 会话静默刷新中（轮询或手动刷新），不切 loading，避免整块面板闪烁。 */
const syncing = ref(false)
const lastSyncedAt = ref<string | null>(null)
let pollTimer: number | null = null

const resolveDialog = ref(false)
const resolutionSummary = ref('')
const closeDialog = ref(false)
const closeReason = ref('')
const archiveDialog = ref(false)
const archiveReason = ref('')

const assistantMessages = computed(
  () => conversation.value?.messages.filter((message) => message.role === 'assistant') ?? [],
);

/**
 * 「这个工单现在归我处理吗」。
 *
 * 优先用后端 `assigned_to_me`（权威）；字段缺失说明后端还是旧版本（镜像未重建 /
 * 滚动发布中的旧实例），此时退回本机接管备忘，避免把自己刚接管的工单误判成
 * 「别人接管的」而永久锁死回复功能。
 */
const assignedToMe = computed<boolean>(() => {
  const current = ticket.value
  if (!current) return false
  if (typeof current.assigned_to_me === 'boolean') return current.assigned_to_me
  return hasTakeoverMemory(currentUserId.value, current.ticket_id)
})

/**
 * 为什么现在不能回复。`null` 表示「我已接管，可以写」。
 * 与后端 `ensure_reply_allowed` 的四条判断一一对应，避免前端放行、后端 409 的错位。
 */
const replyBlockedReason = computed<string | null>(() => {
  const current = ticket.value
  if (!current) return '工单加载中，暂不可回复。'
  if (current.status === 'open') return '工单尚未接管，需先点击「接管」才能回复用户。'
  if (current.status === 'resolved') return '工单已标记解决，不能再回复用户。'
  if (current.status === 'closed') return '工单已关闭，不能再回复用户。'
  if (!assignedToMe.value) {
    return `该工单已由 ${current.assigned_to_masked ?? '其他客服'} 接管，如需回复请先接管。`
  }
  return null
})

/** 接管后（且由我接管）才允许回复、打分、解决、关闭。 */
const canReply = computed(() => replyBlockedReason.value === null)

/** 可接管的场景：待处理，或已被别人接管（接管即转由我处理）。已归我则无需再接管。 */
const canTakeOver = computed(
  () => ticket.value?.status === 'open' || (ticket.value?.status === 'assigned' && !assignedToMe.value),
)

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  transcriptError.value = null
  conversation.value = null
  try {
    const fetched = await supportApi.ticket(ticketId)
    ticket.value = fetched
    // 后端给了权威值就顺手校正本地备忘，避免旧记录盖住服务端事实。
    if (typeof fetched.assigned_to_me === 'boolean') {
      syncTakeoverMemory(currentUserId.value, fetched.ticket_id, fetched.assigned_to_me)
    }
  } catch (caught) {
    error.value = toApiError(caught)
    loading.value = false
    return
  }
  // 会话可能已被用户删除：工单元数据仍然有效，单独吸收这个错误。
  try {
    conversation.value = await supportApi.conversation(ticket.value.conversation_id)
  } catch (caught) {
    transcriptError.value = toApiError(caught).message
  } finally {
    loading.value = false
  }
}

/**
 * 只刷新会话，不动加载态。
 *
 * 客服在详情页等用户回话，原来只在 `onMounted` 拉一次，用户再发消息（或换账号）都
 * 看不到，表现就是「发的出去、收不到」。这里供 10 秒轮询与手动刷新复用。
 */
async function syncConversation(): Promise<void> {
  const current = ticket.value
  if (!current || syncing.value) return
  syncing.value = true
  try {
    conversation.value = await supportApi.conversation(current.conversation_id)
    transcriptError.value = null
    lastSyncedAt.value = new Date().toISOString()
  } catch (caught) {
    transcriptError.value = toApiError(caught).message
  } finally {
    syncing.value = false
  }
}

async function runAction(
  action: 'assign' | 'resolve' | 'close' | 'archive',
  extra: Record<string, unknown> = {},
): Promise<void> {
  actionLoading.value = true
  actionError.value = null
  actionNotice.value = ''
  try {
    const result = await supportApi.patchTicket(ticketId, { action, ...extra } as never)
    // 后端 `assign` 在未指定 assignee 时把处理人设为调用者，所以「我这边成功」即
    // 「工单归我」。先记下来：即使后端还是旧版本、详情不返回 `assigned_to_me`，
    // 接管后也能立刻解锁回复，而不是把按钮和输入框永久卡在未接管状态。
    if (action === 'assign') rememberTakeover(currentUserId.value, ticketId)
    actionNotice.value = `已更新：${ticketStatusLabel(result.status)}`
    await load()
  } catch (caught) {
    actionError.value = toApiError(caught)
  } finally {
    actionLoading.value = false
  }
}

async function sendReply(): Promise<void> {
  const content = replyDraft.value.trim()
  if (!content || replySending.value) return
  // 兜底：按钮本身已禁用，这里再拦一次，避免状态竞态下把消息发进别人的工单。
  if (replyBlockedReason.value) {
    ElMessage.warning(replyBlockedReason.value)
    return
  }
  replySending.value = true
  actionError.value = null
  try {
    await supportApi.reply(ticketId, { content })
    replyDraft.value = ''
    actionNotice.value = '回复已发送，用户会在原会话中看到'
    // 只刷会话：走 load() 会把 conversation 置空，面板闪一下「加载中」。
    await syncConversation()
  } catch (caught) {
    actionError.value = toApiError(caught)
  } finally {
    replySending.value = false
  }
}

async function onAssign(): Promise<void> {
  const current = ticket.value
  const takenByOther =
    current?.status === 'assigned' && !assignedToMe.value
      ? (current.assigned_to_masked ?? '其他客服')
      : null
  try {
    await ElMessageBox.confirm(
      takenByOther
        ? `该工单当前由 ${takenByOther} 接管，接管后将转由你跟进处理。是否继续？`
        : '接管该工单？接管后由你跟进处理；未接管前无法回复用户或处理该工单。',
      '接管工单',
      {
        confirmButtonText: '接管',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }
  await runAction('assign')
}

async function onResolve(): Promise<void> {
  if (resolutionSummary.value.trim().length < 1) return
  await runAction('resolve', { resolution_summary: resolutionSummary.value.trim().slice(0, 500) })
  resolveDialog.value = false
  resolutionSummary.value = ''
}

async function onClose(): Promise<void> {
  await runAction('close', { close_reason: closeReason.value.trim() ? closeReason.value.trim().slice(0, 500) : null })
  closeDialog.value = false
  closeReason.value = ''
}

const canResolve = computed(() => resolutionSummary.value.trim().length >= 1)
const canArchive = computed(() => archiveReason.value.trim().length >= 2)

async function onArchive(): Promise<void> {
  await runAction('archive', { close_reason: archiveReason.value.trim().slice(0, 240) })
  archiveDialog.value = false
  archiveReason.value = ''
}

onMounted(() => {
  void load()
  // 详情页停留期间定时拉会话：客服等的是用户回话，只在挂载时拉一次等于「收不到回复」。
  pollTimer = window.setInterval(() => {
    if (document.visibilityState !== 'visible') return
    if (loading.value || actionLoading.value || replySending.value || syncing.value) return
    // 已关闭的工单不会再有新消息，不必继续空转拉取。
    if (ticket.value?.status === 'closed') return
    void syncConversation()
  }, CONVERSATION_POLL_MS)
})

onUnmounted(() => {
  if (pollTimer !== null) window.clearInterval(pollTimer)
  pollTimer = null
})
</script>

<template>
  <div class="sm-page">
    <div class="sm-between">
      <h2 class="sm-page-title">工单详情</h2>
      <ElButton size="small" @click="router.push('/support')">返回队列</ElButton>
    </div>

    <StateBlock :loading="loading && !ticket" :error="error" :empty="!loading && !error && !ticket" empty-text="未找到工单或无权访问。" @retry="load">
      <template v-if="ticket">
        <div class="sm-card">
          <div class="sm-between">
            <div>
              <p class="sm-ticket-id">工单 <span class="sm-mono">{{ ticket.ticket_id }}</span></p>
              <p class="sm-muted">
                状态：{{ ticketStatusLabel(ticket.status) }} · 风险：{{ riskLevelLabel(ticket.risk_level) }} ·
                优先级 P{{ ticket.priority }} · 队列 {{ ticket.queue }} ·
                主因 {{ handoffReasonLabel(ticket.primary_reason_code) }}
              </p>
              <p class="sm-muted">
                用户（脱敏）：{{ ticket.user_reference_masked }} ·
                接管人：{{ ticket.assigned_to_masked ?? '暂未接管' }} ·
                创建 {{ formatDateTime(ticket.created_at) }} · 更新 {{ formatDateTime(ticket.updated_at) }}
              </p>
            </div>
            <div class="sm-row sm-actions">
              <ElTag
                v-if="assignedToMe && ticket.status !== 'closed'"
                size="small"
                type="success"
                effect="light"
              >
                已接管
              </ElTag>
              <ElButton
                v-if="canTakeOver"
                size="small"
                type="primary"
                :loading="actionLoading"
                @click="onAssign"
              >
                接管
              </ElButton>
              <ElButton
                v-if="ticket.status === 'assigned' && assignedToMe"
                size="small"
                type="success"
                :loading="actionLoading"
                @click="resolveDialog = true"
              >
                标记解决
              </ElButton>
              <ElButton
                v-if="ticket.status === 'resolved' && assignedToMe"
                size="small"
                :loading="actionLoading"
                @click="closeDialog = true"
              >
                关闭工单
              </ElButton>
              <ElButton
                v-if="!ticket.transcript_available && ticket.status !== 'closed'"
                size="small"
                plain
                :loading="actionLoading"
                @click="archiveDialog = true"
              >
                归档
              </ElButton>
            </div>
          </div>
          <p v-if="ticket.summary_redacted" class="sm-ticket-summary">安全摘要：{{ ticket.summary_redacted }}</p>
          <p v-if="ticket.expected_response" class="sm-muted">预计响应：{{ ticket.expected_response }}</p>
        </div>

        <ElAlert v-if="actionNotice" type="success" :closable="false" show-icon :title="actionNotice" class="sm-alert" />
        <ElAlert v-if="actionError" type="error" :closable="false" show-icon :title="actionError.message" class="sm-alert" />

        <div class="sm-card">
          <div class="sm-row sm-conversation-toolbar">
            <ElButton size="small" :loading="syncing" @click="syncConversation">刷新会话</ElButton>
            <span class="sm-muted">
              每 10 秒自动刷新{{ lastSyncedAt ? ` · 最近 ${formatDateTime(lastSyncedAt)}` : '' }}
            </span>
          </div>
          <SupportConversationPanel v-if="conversation" :conversation="conversation" />
          <ElAlert
            v-else-if="transcriptError"
            type="warning"
            :closable="false"
            show-icon
            :title="transcriptError"
            description="该工单的会话已不可访问，聊天记录、回复与打分均不可用；你仍可查看工单元数据并归档。"
          />
          <p v-else class="sm-muted">会话加载中或不可用。</p>
        </div>

        <div v-if="ticket.transcript_available" class="sm-card">
          <h3 class="sm-section-title">回复用户</h3>
          <p class="sm-muted">
            回复会写入同一会话，用户在聊天页可直接看到；内容会经过 PII 脱敏检查，不展示内部字段。
          </p>
          <ElAlert
            v-if="!canReply"
            type="info"
            :closable="false"
            show-icon
            :title="replyBlockedReason ?? ''"
            description="未接管的工单只读：可以先查看会话判断是否需要处理，接管后才能回复用户。"
            class="sm-reply-locked"
          />
          <ElAlert
            v-else
            type="success"
            :closable="false"
            show-icon
            title="已接管：可以回复用户、对 AI 回答打分，处理完可标记解决。"
            class="sm-reply-unlocked"
          />
          <ElInput
            v-model="replyDraft"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            :disabled="!canReply"
            placeholder="例如：你好，我是人工客服，已收到你的退款申请，正在核实订单状态，预计今天内回复你。"
          />
          <div class="sm-row sm-reply-actions">
            <ElButton
              type="primary"
              :loading="replySending"
              :disabled="!canReply || !replyDraft.trim()"
              @click="sendReply"
            >
              发送回复
            </ElButton>
            <ElButton v-if="canTakeOver" :loading="actionLoading" @click="onAssign">接管后回复</ElButton>
            <span class="sm-muted">回复不会触发退款或赔偿，只作为沟通记录。</span>
          </div>
        </div>

        <div v-if="ticket.transcript_available" class="sm-card">
          <h3 class="sm-section-title">对 AI 回答打分</h3>
          <p class="sm-muted">仅可标记授权会话内的助手消息；标记进入评测样本，不直接修改知识或模型。</p>
          <p v-if="!canReply" class="sm-muted">接管该工单后才能打分。</p>
          <QualityLabelForm
            v-for="message in assistantMessages"
            :key="message.message_id"
            :assistant-message-id="message.message_id"
            :disabled="!canReply"
          />
          <p v-if="!assistantMessages.length" class="sm-muted">该会话暂无可标记的助手消息。</p>
        </div>
      </template>
    </StateBlock>

    <ElDialog v-model="resolveDialog" title="标记解决" width="min(30rem, 94vw)">
      <ElInput
        v-model="resolutionSummary"
        type="textarea"
        :rows="4"
        maxlength="500"
        show-word-limit
        placeholder="解决摘要（1-500 字符）"
      />
      <template #footer>
        <ElButton @click="resolveDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="actionLoading" :disabled="!canResolve" @click="onResolve">确认解决</ElButton>
      </template>
    </ElDialog>

    <ElDialog v-model="archiveDialog" title="归档工单" width="min(30rem, 94vw)">
      <p class="sm-muted">
        归档用于「会话已不存在、无法继续处理」的工单：工单会置为已关闭并写入审计，不会被物理删除。
      </p>
      <ElInput
        v-model="archiveReason"
        type="textarea"
        :rows="3"
        maxlength="240"
        show-word-limit
        placeholder="归档原因（必填，例如：会话已被用户删除，无法取证）"
      />
      <template #footer>
        <ElButton @click="archiveDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="actionLoading" :disabled="!canArchive" @click="onArchive">
          确认归档
        </ElButton>
      </template>
    </ElDialog>

    <ElDialog v-model="closeDialog" title="关闭工单" width="min(30rem, 94vw)">
      <ElInput v-model="closeReason" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="关闭原因（可选）" />
      <template #footer>
        <ElButton @click="closeDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="actionLoading" @click="onClose">确认关闭</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0;
  font-size: 18px;
}

.sm-ticket-id {
  margin: 0 0 4px;
  font-weight: 700;
}

.sm-ticket-summary {
  margin: 8px 0 0;
}

.sm-alert {
  margin-bottom: 12px;
}

.sm-card {
  margin-bottom: 12px;
}

.sm-section-title {
  margin: 0 0 6px;
  font-size: 15px;
}

.sm-actions {
  flex: none;
}

.sm-conversation-toolbar {
  justify-content: space-between;
  margin-bottom: 8px;
}

.sm-reply-unlocked {
  margin-bottom: 8px;
}

.sm-reply-actions {
  margin-top: 10px;
  justify-content: space-between;
  flex-wrap: wrap;
}

.sm-reply-locked {
  margin-bottom: 10px;
}
</style>
