<script setup lang="ts">
/**
 * 工单详情：安全摘要 + 会话解释（消息/引用/工具/风险）+ 接管/解决/关闭。
 * 状态转换由后端校验（docs/06-api.md 第 12 节状态机），前端只提交动作。
 */

import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElAlert, ElButton, ElDialog, ElInput, ElMessageBox } from 'element-plus'

import QualityLabelForm from '@/components/support/QualityLabelForm.vue'
import SupportConversationPanel from '@/components/support/SupportConversationPanel.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { supportApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { SupportConversation, SupportTicketDetail } from '@/api/types'
import { formatDateTime, handoffReasonLabel, riskLevelLabel, ticketStatusLabel } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const ticketId = String(route.params.ticketId ?? '')

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

const resolveDialog = ref(false)
const resolutionSummary = ref('')
const closeDialog = ref(false)
const closeReason = ref('')
const archiveDialog = ref(false)
const archiveReason = ref('')

const assistantMessages = computed(
  () => conversation.value?.messages.filter((message) => message.role === 'assistant') ?? [],
);

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  transcriptError.value = null
  conversation.value = null
  try {
    ticket.value = await supportApi.ticket(ticketId)
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

async function runAction(
  action: 'assign' | 'resolve' | 'close' | 'archive',
  extra: Record<string, unknown> = {},
): Promise<void> {
  actionLoading.value = true
  actionError.value = null
  actionNotice.value = ''
  try {
    const result = await supportApi.patchTicket(ticketId, { action, ...extra } as never)
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
  replySending.value = true
  actionError.value = null
  try {
    await supportApi.reply(ticketId, { content })
    replyDraft.value = ''
    actionNotice.value = '回复已发送，用户会在原会话中看到'
    await load()
  } catch (caught) {
    actionError.value = toApiError(caught)
  } finally {
    replySending.value = false
  }
}

async function onAssign(): Promise<void> {
  try {
    await ElMessageBox.confirm('接管该工单？接管后由你跟进处理。', '接管工单', {
      confirmButtonText: '接管',
      cancelButtonText: '取消',
      type: 'warning',
    })
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

onMounted(load)
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
                创建 {{ formatDateTime(ticket.created_at) }} · 更新 {{ formatDateTime(ticket.updated_at) }}
              </p>
            </div>
            <div class="sm-row sm-actions">
              <ElButton
                v-if="ticket.status === 'open' || ticket.status === 'assigned'"
                size="small"
                type="primary"
                :loading="actionLoading"
                @click="onAssign"
              >
                接管
              </ElButton>
              <ElButton
                v-if="ticket.status === 'assigned'"
                size="small"
                type="success"
                :loading="actionLoading"
                @click="resolveDialog = true"
              >
                标记解决
              </ElButton>
              <ElButton
                v-if="ticket.status === 'resolved'"
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
          <ElInput
            v-model="replyDraft"
            type="textarea"
            :rows="3"
            maxlength="2000"
            show-word-limit
            placeholder="例如：你好，我是人工客服，已收到你的退款申请，正在核实订单状态，预计今天内回复你。"
          />
          <div class="sm-row sm-reply-actions">
            <ElButton type="primary" :loading="replySending" :disabled="!replyDraft.trim()" @click="sendReply">
              发送回复
            </ElButton>
            <span class="sm-muted">回复不会触发退款或赔偿，只作为沟通记录。</span>
          </div>
        </div>

        <div v-if="ticket.transcript_available" class="sm-card">
          <h3 class="sm-section-title">对 AI 回答打分</h3>
          <p class="sm-muted">仅可标记授权会话内的助手消息；标记进入评测样本，不直接修改知识或模型。</p>
          <QualityLabelForm
            v-for="message in assistantMessages"
            :key="message.message_id"
            :assistant-message-id="message.message_id"
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

.sm-reply-actions {
  margin-top: 10px;
  justify-content: space-between;
  flex-wrap: wrap;
}
</style>
