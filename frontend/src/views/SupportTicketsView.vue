<script setup lang="ts">
/**
 * 客服工作台：工单队列 + 退款待办。
 *
 * 两个列表都只返回当前店铺的数据（后端校验），前端筛选不构成安全边界。
 * 退款审批是人工动作：通过/拒绝都必须留下说明，拒绝时说明必填。
 *
 * 工单驳回同样是人工动作，且**不删除任何数据**：复用状态机的 archive 迁移
 * （open/assigned/resolved → closed，close_reason 必填、写审计），
 * 工单与聊天记录都留在库里，用户侧仍能看到关闭原因。
 */

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  ElAlert,
  ElButton,
  ElCheckbox,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
  ElTag,
} from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { supportApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { RefundItem, SupportTicketListItem } from '@/api/types'
import {
  formatDateTime,
  formatMoney,
  formatWaiting,
  handoffReasonLabel,
  refundStatusLabel,
  refundStatusTagType,
  returnReasonLabel,
  riskLevelLabel,
  ticketStatusLabel,
} from '@/utils/format'

const router = useRouter()

const tab = ref<'tickets' | 'refunds'>('tickets')

const loading = ref(true)
const error = ref<ApiError | null>(null)
const tickets = ref<SupportTicketListItem[]>([])
const statusFilter = ref('')
const riskFilter = ref('')
/** 默认只看能打开聊天记录的工单；会话已被删除的工单需显式打开才显示。 */
const includeClosedTranscripts = ref(false)

const refundLoading = ref(true)
const refundError = ref<ApiError | null>(null)
const refunds = ref<RefundItem[]>([])
const refundStatus = ref('requested')
const reviewing = ref<string | null>(null)

const deadTranscriptCount = computed(() => tickets.value.filter((item) => !item.transcript_available).length)
const pendingRefunds = computed(() => refunds.value.filter((item) => item.status === 'requested'))

/** 可驳回状态：已解决 / 已关闭的工单不参与驳回（前者应走「关闭」，后者已终结）。 */
const REJECTABLE_STATUS = ['open', 'assigned'] as const

function isRejectable(row: SupportTicketListItem): boolean {
  return (REJECTABLE_STATUS as readonly string[]).includes(row.status)
}

/** 勾选的工单 id。只存 id，列表刷新后由 pruneSelection 剔除已不可驳回的行。 */
const selectedIds = ref<string[]>([])
const rejecting = ref(false)
/** 批量驳回的失败明细：不用 toast 吞掉，留在页面上可查。 */
const rejectFailures = ref<Array<{ ticketId: string; message: string }>>([])

const rejectableTickets = computed(() => tickets.value.filter(isRejectable))
const rejectableCount = computed(() => rejectableTickets.value.length)
const allSelected = computed(
  () => rejectableCount.value > 0 && selectedIds.value.length === rejectableCount.value,
)
const partlySelected = computed(() => selectedIds.value.length > 0 && !allSelected.value)

function setSelected(ticketId: string, checked: unknown): void {
  const target = tickets.value.find((row) => row.ticket_id === ticketId)
  if (!target || !isRejectable(target)) return
  const next = new Set(selectedIds.value)
  if (checked) next.add(ticketId)
  else next.delete(ticketId)
  selectedIds.value = [...next]
}

function toggleSelectAll(checked: unknown): void {
  selectedIds.value = checked ? rejectableTickets.value.map((row) => row.ticket_id) : []
}

function onSelectAllChange(checked: unknown): void {
  toggleSelectAll(Boolean(checked))
}

function onRowChange(ticketId: string, checked: unknown): void {
  setSelected(ticketId, Boolean(checked))
}

/** 列表刷新后，把已不在「可驳回」集合里的 id 从选中项里去掉，避免批量操作打到旧数据。 */
function pruneSelection(): void {
  const allowed = new Set(rejectableTickets.value.map((row) => row.ticket_id))
  selectedIds.value = selectedIds.value.filter((id) => allowed.has(id))
}

async function loadTickets(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const data = await supportApi.tickets({
      status: statusFilter.value || undefined,
      risk_level: riskFilter.value || undefined,
      transcript: includeClosedTranscripts.value ? 'all' : 'available',
      limit: 50,
    })
    tickets.value = data.items
    pruneSelection()
  } catch (caught) {
    error.value = toApiError(caught)
    tickets.value = []
  } finally {
    loading.value = false
  }
}

async function loadRefunds(): Promise<void> {
  refundLoading.value = true
  refundError.value = null
  try {
    const data = await supportApi.refunds({
      status: refundStatus.value || undefined,
      limit: 50,
    })
    refunds.value = data.items
  } catch (caught) {
    refundError.value = toApiError(caught)
    refunds.value = []
  } finally {
    refundLoading.value = false
  }
}

function riskType(level: string): 'danger' | 'warning' | 'info' {
  if (level === 'critical' || level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

/**
 * 批量驳回：一次确认 + 一次填写原因，然后对每条工单各自调用 PATCH。
 *
 * 之所以逐条调用而不是新造批量接口：后端每次迁移都会写一条审计（谁、从什么状态到什么状态、
 * 有没有原因），逐条调用才能保证「哪几条成功、哪几条失败」可以逐条追溯；部分失败也不会
 * 让整批回滚成一个说不清的结果。选中的工单最多就是当前页的 50 条。
 */
async function rejectSelected(): Promise<void> {
  if (rejecting.value) return
  const targets = tickets.value.filter(
    (row) => selectedIds.value.includes(row.ticket_id) && isRejectable(row),
  )
  if (!targets.length) {
    ElMessage.warning('请先选择要驳回的工单')
    return
  }

  const deadCount = targets.filter((row) => !row.transcript_available).length
  const deadNote = deadCount ? `，其中 ${deadCount} 条的会话已被用户删除（只关闭工单，不影响会话）` : ''
  let reason = ''
  try {
    const result = await ElMessageBox.prompt(
      `将驳回并关闭选中的 ${targets.length} 条工单${deadNote}。驳回原因会写入工单记录与审计日志；关闭后不可撤销，工单数据不会被删除。`,
      `批量驳回 ${targets.length} 条工单`,
      {
        confirmButtonText: '确认驳回',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '例如：重复提交 / 信息不足无法受理 / 非本店售后范围',
        inputValidator: (value: string) =>
          (value && value.trim().length >= 2) || '请填写至少 2 个字的驳回原因',
      },
    )
    reason = String(result.value ?? '').trim()
  } catch {
    // 用户取消：什么都不做，保留当前选择。
    return
  }
  if (!reason) return

  rejecting.value = true
  rejectFailures.value = []
  try {
    const results = await Promise.allSettled(
      targets.map((row) =>
        supportApi.patchTicket(row.ticket_id, {
          action: 'archive',
          // 后端 close_reason ≤ 240 字符，前缀固定 5 字，留足裁剪余量。
          close_reason: `批量驳回：${reason}`.slice(0, 240),
        }),
      ),
    )
    const failures = results.flatMap((result, index) =>
      result.status === 'rejected'
        ? [{ ticketId: targets[index].ticket_id, message: toApiError(result.reason).message }]
        : [],
    )
    rejectFailures.value = failures
    const succeeded = targets.length - failures.length

    if (!failures.length) {
      ElMessage.success(`已驳回 ${succeeded} 条工单`)
    } else if (succeeded) {
      ElMessage.warning(`已驳回 ${succeeded} 条，${failures.length} 条失败，失败明细见列表上方`)
    } else {
      ElMessage.error(`驳回失败：${failures[0].message}`)
    }

    selectedIds.value = []
    await loadTickets()
  } finally {
    rejecting.value = false
  }
}

async function review(row: RefundItem, approve: boolean): Promise<void> {
  let note = ''
  if (approve) {
    try {
      await ElMessageBox.confirm(
        `通过后将按 ${formatMoney(row.amount_cents, 'CNY')} 发起原路退回（模拟）。确认通过？`,
        '通过退款',
        { confirmButtonText: '通过', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  } else {
    try {
      const result = await ElMessageBox.prompt('请填写拒绝原因（会展示给用户）', '拒绝退款', {
        confirmButtonText: '确认拒绝',
        cancelButtonText: '取消',
        inputType: 'textarea',
        inputPlaceholder: '例如：商品已签收超过 7 天，且非质量问题',
        inputValidator: (value: string) => (value && value.trim().length >= 2) || '请填写至少 2 个字',
      })
      note = String(result.value ?? '').trim()
    } catch {
      return
    }
  }
  reviewing.value = row.id
  try {
    await supportApi.reviewRefund(row.id, { approve, review_note: note || null })
    ElMessage.success(approve ? '已通过退款申请' : '已拒绝退款申请')
    await Promise.all([loadRefunds(), loadTickets()])
  } catch (caught) {
    ElMessage.error(toApiError(caught).message)
  } finally {
    reviewing.value = null
  }
}

onMounted(async () => {
  await Promise.all([loadTickets(), loadRefunds()])
})
</script>

<template>
  <div class="sm-page">
    <div class="sm-page-header">
      <div>
        <h2 class="sm-page-title">客服工作台</h2>
        <p class="sm-page-subtitle">工单优先级由风险与等待时长决定；退款必须人工审核后才原路退回。</p>
      </div>
      <ElButton @click="loadTickets(); loadRefunds()">刷新</ElButton>
    </div>

    <!-- 只保留退款待办计数：「待处理工单」「高风险工单」两张统计卡已下线（数据不受影响，
         仍可通过下方状态/风险筛选查看），避免同一份队列在顶部和列表里重复曝光。 -->
    <div class="sm-stats">
      <div class="sm-stat">
        <span class="sm-stat-label">待审核退款</span>
        <strong>{{ pendingRefunds.length }}</strong>
      </div>
    </div>

    <div class="sm-tabs">
      <button
        type="button"
        class="sm-tab"
        :class="{ 'sm-tab-active': tab === 'tickets' }"
        @click="tab = 'tickets'"
      >
        工单队列
      </button>
      <button
        type="button"
        class="sm-tab"
        :class="{ 'sm-tab-active': tab === 'refunds' }"
        @click="tab = 'refunds'"
      >
        退款审核
        <span v-if="pendingRefunds.length" class="sm-tab-badge">{{ pendingRefunds.length }}</span>
      </button>
    </div>

    <!-- 工单 -->
    <section v-show="tab === 'tickets'">
      <div class="sm-row-wrap sm-filter-bar">
        <ElSelect v-model="statusFilter" placeholder="全部状态" clearable style="width: 9rem" @change="loadTickets">
          <ElOption value="open" label="待处理" />
          <ElOption value="assigned" label="已接管" />
          <ElOption value="resolved" label="已解决" />
          <ElOption value="closed" label="已关闭" />
        </ElSelect>
        <ElSelect v-model="riskFilter" placeholder="全部风险" clearable style="width: 9rem" @change="loadTickets">
          <ElOption value="low" label="低风险" />
          <ElOption value="medium" label="中风险" />
          <ElOption value="high" label="高风险" />
          <ElOption value="critical" label="紧急" />
        </ElSelect>
        <label class="sm-toggle">
          <input v-model="includeClosedTranscripts" type="checkbox" @change="loadTickets" />
          包含会话已删除的工单
        </label>
        <span v-if="deadTranscriptCount" class="sm-muted">
          其中 {{ deadTranscriptCount }} 条会话已删除，只能归档
        </span>
      </div>

      <div v-if="rejectableCount" class="sm-bulk-bar">
        <ElCheckbox
          :model-value="allSelected"
          :indeterminate="partlySelected"
          :disabled="rejecting"
          @change="onSelectAllChange"
        >
          全选可驳回（{{ rejectableCount }}）
        </ElCheckbox>
        <span class="sm-muted">已选 {{ selectedIds.length }} 条</span>
        <ElButton
          size="small"
          type="danger"
          plain
          :disabled="!selectedIds.length || rejecting"
          :loading="rejecting"
          @click="rejectSelected"
        >
          批量驳回
        </ElButton>
        <span class="sm-muted sm-bulk-hint">驳回 = 关闭工单并记录原因，不删除工单与聊天记录</span>
      </div>

      <ElAlert
        v-if="rejectFailures.length"
        class="sm-block"
        type="warning"
        :closable="false"
        show-icon
        title="部分工单驳回失败，可重试或逐条处理"
      >
        <ul class="sm-failure-list">
          <li v-for="item in rejectFailures" :key="item.ticketId">
            <span class="sm-mono">{{ item.ticketId }}</span>：{{ item.message }}
          </li>
        </ul>
      </ElAlert>

      <StateBlock
        :loading="loading && !tickets.length"
        :error="error"
        :empty="!loading && !error && tickets.length === 0"
        empty-text="当前没有需要处理的工单。"
        @retry="loadTickets"
      >
        <div class="sm-ticket-list">
          <article
            v-for="row in tickets"
            :key="row.ticket_id"
            class="sm-ticket-card sm-card-hover"
            @click="router.push(`/support/tickets/${row.ticket_id}`)"
          >
            <div class="sm-ticket-top">
              <!-- 勾选只负责选中，不触发卡片跳转；已解决/已关闭不可驳回，勾选框置灰 -->
              <ElCheckbox
                class="sm-ticket-check"
                :model-value="selectedIds.includes(row.ticket_id)"
                :disabled="!isRejectable(row) || rejecting"
                :title="isRejectable(row) ? '选择此工单用于批量驳回' : '已解决 / 已关闭的工单不能驳回'"
                @click.stop
                @change="onRowChange(row.ticket_id, $event)"
              />
              <ElTag size="small" :type="riskType(row.risk_level)" effect="light">
                {{ riskLevelLabel(row.risk_level) }}风险
              </ElTag>
              <span class="sm-ticket-reason">{{ handoffReasonLabel(row.primary_reason_code) }}</span>
              <ElTag size="small" effect="plain">{{ ticketStatusLabel(row.status) }}</ElTag>
              <ElTag v-if="!row.transcript_available" size="small" type="info" effect="plain">
                会话已删除
              </ElTag>
              <span class="sm-ticket-priority">P{{ row.priority }}</span>
              <span class="sm-muted sm-ticket-wait">已等待 {{ formatWaiting(row.waiting_seconds) }}</span>
            </div>
            <p class="sm-ticket-id sm-mono">工单 {{ row.ticket_id }}</p>
            <p class="sm-muted">
              用户 {{ row.user_reference_masked }}
              <template v-if="row.assigned_to_masked"> · 负责人 {{ row.assigned_to_masked }}</template>
              · 队列 {{ row.queue }}
              · {{ formatDateTime(row.created_at) }}
            </p>
            <div class="sm-row-wrap">
              <span v-for="code in row.reason_codes" :key="code" class="sm-chip">{{ handoffReasonLabel(code) }}</span>
            </div>
          </article>
        </div>
      </StateBlock>
    </section>

    <!-- 退款 -->
    <section v-show="tab === 'refunds'">
      <div class="sm-row-wrap sm-filter-bar">
        <ElSelect v-model="refundStatus" placeholder="全部状态" clearable style="width: 10rem" @change="loadRefunds">
          <ElOption value="requested" label="待审核" />
          <ElOption value="approved" label="已通过" />
          <ElOption value="rejected" label="已拒绝" />
          <ElOption value="completed" label="已完成" />
        </ElSelect>
        <span class="sm-muted">共 {{ refunds.length }} 笔</span>
      </div>

      <StateBlock
        :loading="refundLoading && !refunds.length"
        :error="refundError"
        :empty="!refundLoading && !refundError && refunds.length === 0"
        empty-text="当前没有退款申请。"
        @retry="loadRefunds"
      >
        <div class="sm-refund-list">
          <article v-for="row in refunds" :key="row.id" class="sm-refund-card">
            <div class="sm-between">
              <div>
                <p class="sm-refund-no sm-mono">{{ row.refund_no }}</p>
                <p class="sm-muted">
                  订单 <router-link :to="`/orders/${row.order_id}`">{{ row.order_no }}</router-link>
                  · {{ row.scope === 'order' ? '整单退款' : '单件退款' }}
                  · {{ returnReasonLabel(row.reason_code) }}
                  · {{ formatDateTime(row.created_at) }}
                </p>
                <p v-if="row.note" class="sm-muted">用户说明：{{ row.note }}</p>
                <p v-if="row.review_note" class="sm-muted">审核说明：{{ row.review_note }}</p>
              </div>
              <div class="sm-refund-right">
                <strong class="sm-price">{{ formatMoney(row.amount_cents, 'CNY') }}</strong>
                <ElTag size="small" :type="refundStatusTagType(row.status)">
                  {{ refundStatusLabel(row.status) }}
                </ElTag>
              </div>
            </div>
            <div v-if="row.status === 'requested'" class="sm-refund-actions">
              <ElButton
                size="small"
                type="success"
                :loading="reviewing === row.id"
                @click="review(row, true)"
              >
                通过并退款
              </ElButton>
              <ElButton
                size="small"
                type="danger"
                plain
                :loading="reviewing === row.id"
                @click="review(row, false)"
              >
                拒绝
              </ElButton>
            </div>
          </article>
        </div>
      </StateBlock>
    </section>
  </div>
</template>

<style scoped>
.sm-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.sm-stat {
  flex: 1 1 180px;
  max-width: 260px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 14px 18px;
  border-radius: var(--sm-radius);
  background: var(--sm-surface);
  border: 1px solid var(--sm-border);
  box-shadow: var(--sm-shadow-xs);
}

.sm-stat-label {
  font-size: 12px;
  color: var(--sm-text-secondary);
}

.sm-stat strong {
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}

/* ---- 批量驳回 ------------------------------------------------------- */

.sm-bulk-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 8px 12px;
  margin-bottom: 10px;
  border: 1px solid var(--sm-border);
  border-radius: var(--sm-radius);
  background: var(--sm-surface);
  box-shadow: var(--sm-shadow-xs);
}

.sm-bulk-hint {
  margin-left: auto;
  font-size: 12px;
}

.sm-ticket-check {
  margin-right: 2px;
}

.sm-failure-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
}

.sm-block {
  margin-bottom: 10px;
}

.sm-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
}

.sm-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 999px;
  border: 1px solid var(--sm-border);
  background: var(--sm-surface);
  color: var(--sm-text-secondary);
  cursor: pointer;
  font-size: 13px;
}

.sm-tab-active {
  background: var(--sm-primary);
  border-color: var(--sm-primary);
  color: #fff;
  font-weight: 600;
}

.sm-tab-badge {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-accent);
  color: #fff;
  font-size: 10px;
}

.sm-filter-bar {
  margin-bottom: 12px;
}

.sm-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--sm-text-secondary);
  cursor: pointer;
}

.sm-ticket-list,
.sm-refund-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sm-ticket-card {
  padding: 14px 16px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sm-ticket-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sm-ticket-reason {
  font-weight: 650;
  font-size: 14px;
}

.sm-ticket-priority {
  font-size: 11px;
  padding: 0 7px;
  border-radius: 6px;
  background: var(--sm-bg);
  border: 1px solid var(--sm-border);
  color: var(--sm-text-secondary);
}

.sm-ticket-wait {
  margin-left: auto;
}

.sm-ticket-id {
  margin: 0;
  font-size: 12px;
  color: var(--sm-text-secondary);
}

.sm-refund-card {
  padding: 14px 16px;
  background: var(--sm-surface);
  border: 1px solid var(--sm-border);
  border-radius: var(--sm-radius);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sm-refund-no {
  margin: 0 0 2px;
  font-weight: 650;
  font-size: 13px;
}

.sm-refund-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.sm-refund-right strong {
  font-size: 18px;
}

.sm-refund-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  border-top: 1px dashed var(--sm-border);
  padding-top: 10px;
}

@media (max-width: 768px) {
  .sm-stat {
    max-width: none;
  }

  .sm-bulk-hint {
    margin-left: 0;
  }
}
</style>
