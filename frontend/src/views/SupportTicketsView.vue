<script setup lang="ts">
/**
 * 客服工作台：工单队列 + 退款待办。
 *
 * 两个列表都只返回当前店铺的数据（后端校验），前端筛选不构成安全边界。
 * 退款审批是人工动作：通过/拒绝都必须留下说明，拒绝时说明必填。
 */

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElMessage, ElMessageBox, ElOption, ElSelect, ElTag } from 'element-plus'

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

const refundLoading = ref(true)
const refundError = ref<ApiError | null>(null)
const refunds = ref<RefundItem[]>([])
const refundStatus = ref('requested')
const reviewing = ref<string | null>(null)

const openCount = computed(() => tickets.value.filter((item) => item.status === 'open').length)
const riskyCount = computed(
  () => tickets.value.filter((item) => ['high', 'critical'].includes(item.risk_level)).length,
)
const pendingRefunds = computed(() => refunds.value.filter((item) => item.status === 'requested'))

async function loadTickets(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const data = await supportApi.tickets({
      status: statusFilter.value || undefined,
      risk_level: riskFilter.value || undefined,
      limit: 50,
    })
    tickets.value = data.items
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

    <div class="sm-stats">
      <div class="sm-stat">
        <span class="sm-stat-label">待处理工单</span>
        <strong>{{ openCount }}</strong>
      </div>
      <div class="sm-stat">
        <span class="sm-stat-label">高风险工单</span>
        <strong class="sm-stat-danger">{{ riskyCount }}</strong>
      </div>
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
      </div>

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
              <ElTag size="small" :type="riskType(row.risk_level)" effect="light">
                {{ riskLevelLabel(row.risk_level) }}风险
              </ElTag>
              <span class="sm-ticket-reason">{{ handoffReasonLabel(row.primary_reason_code) }}</span>
              <ElTag size="small" effect="plain">{{ ticketStatusLabel(row.status) }}</ElTag>
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
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.sm-stat {
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

.sm-stat-danger {
  color: var(--sm-danger);
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
  .sm-stats {
    grid-template-columns: 1fr;
  }
}
</style>
