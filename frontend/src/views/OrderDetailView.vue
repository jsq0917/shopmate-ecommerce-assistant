<script setup lang="ts">
/**
 * 订单详情：状态进度、商品明细、支付/取消/退款/退货入口、退款记录与物流。
 *
 * 所有写操作都只提交「动作」，金额与可行性由后端判定；页面不会显示未经服务端确认的
 * 结果（比如"已退款"）。
 */

import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ElAlert,
  ElButton,
  ElDialog,
  ElInput,
  ElMessage,
  ElMessageBox,
  ElOption,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'

import ReturnWizard from '@/components/orders/ReturnWizard.vue'
import ShipmentTimeline from '@/components/orders/ShipmentTimeline.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { ordersApi, refundsApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { OrderDetailData, RefundItem, ShipmentData } from '@/api/types'
import {
  RETURN_REASON_OPTIONS,
  formatDateTime,
  formatMoney,
  orderStatusLabel,
  refundStatusLabel,
  refundStatusTagType,
  returnReasonLabel,
} from '@/utils/format'

const route = useRoute()
const router = useRouter()
const orderId = String(route.params.orderId ?? '')

const loading = ref(true)
const error = ref<ApiError | null>(null)
const order = ref<OrderDetailData | null>(null)
const acting = ref(false)

const shipment = ref<ShipmentData | null>(null)
const shipmentLoading = ref(false)
const shipmentError = ref<ApiError | null>(null)
const shipmentRequested = ref(false)

const refunds = ref<RefundItem[]>([])

const refundDialog = ref(false)
const refundForm = reactive<{ orderItemId: string; reason: string; note: string }>({
  orderItemId: '',
  reason: 'NO_LONGER_NEEDED',
  note: '',
})

const statusSteps = ['created', 'paid', 'processing', 'shipped', 'delivered', 'completed']
const currentStep = computed(() => {
  const status = order.value?.status ?? ''
  if (status === 'cancelled') return -1
  return statusSteps.indexOf(status)
})

const canPay = computed(() => order.value?.status === 'created')
const canCancel = computed(() =>
  ['created', 'paid', 'processing'].includes(order.value?.status ?? ''),
)
const canRefund = computed(() =>
  ['paid', 'processing', 'shipped', 'delivered', 'completed'].includes(order.value?.status ?? ''),
)
const canReturn = computed(() =>
  ['delivered', 'completed'].includes(order.value?.status ?? ''),
)

async function loadOrder(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    order.value = await ordersApi.detail(orderId)
    refunds.value = (await refundsApi.list({ order_id: orderId, limit: 20 })).items
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    loading.value = false
  }
}

async function loadShipment(): Promise<void> {
  shipmentRequested.value = true
  shipmentLoading.value = true
  shipmentError.value = null
  try {
    shipment.value = await ordersApi.shipment(orderId)
  } catch (caught) {
    shipmentError.value = toApiError(caught)
  } finally {
    shipmentLoading.value = false
  }
}

async function pay(): Promise<void> {
  if (!order.value) return
  acting.value = true
  try {
    await ElMessageBox.confirm(
      `确认支付 ${formatMoney(order.value.total_cents, order.value.currency)}？演示环境为模拟支付。`,
      '确认支付',
      { confirmButtonText: '确认支付', cancelButtonText: '再想想' },
    )
  } catch {
    acting.value = false
    return
  }
  try {
    await ordersApi.pay(orderId)
    ElMessage.success('支付成功')
    await loadOrder()
  } catch (caught) {
    ElMessage.error(toApiError(caught).message)
  } finally {
    acting.value = false
  }
}

async function cancel(): Promise<void> {
  try {
    await ElMessageBox.confirm('取消后库存会释放，确认取消这笔订单？', '取消订单', {
      confirmButtonText: '取消订单',
      cancelButtonText: '保留订单',
      type: 'warning',
    })
  } catch {
    return
  }
  acting.value = true
  try {
    await ordersApi.cancel(orderId)
    ElMessage.success('订单已取消')
    await loadOrder()
  } catch (caught) {
    ElMessage.error(toApiError(caught).message)
  } finally {
    acting.value = false
  }
}

function openRefund(orderItemId: string | null = null): void {
  refundForm.orderItemId = orderItemId ?? ''
  refundForm.reason = 'NO_LONGER_NEEDED'
  refundForm.note = ''
  refundDialog.value = true
}

async function submitRefund(): Promise<void> {
  acting.value = true
  try {
    await refundsApi.create({
      order_id: orderId,
      reason_code: refundForm.reason as never,
      order_item_id: refundForm.orderItemId || null,
      note: refundForm.note.trim() || null,
    })
    ElMessage.success('退款申请已提交，客服会尽快审核')
    refundDialog.value = false
    await loadOrder()
  } catch (caught) {
    ElMessage.error(toApiError(caught).message)
  } finally {
    acting.value = false
  }
}

onMounted(async () => {
  await loadOrder()
  if (order.value && ['shipped', 'delivered', 'completed'].includes(order.value.status)) {
    void loadShipment()
  }
})
</script>

<template>
  <div class="sm-page">
    <div class="sm-page-header">
      <div>
        <h2 class="sm-page-title">订单详情</h2>
        <p class="sm-page-subtitle">
          订单号 <span class="sm-mono">{{ order?.order_no ?? '--' }}</span>
        </p>
      </div>
      <ElButton @click="router.push('/orders')">返回订单列表</ElButton>
    </div>

    <StateBlock
      :loading="loading && !order"
      :error="error"
      :empty="!loading && !error && !order"
      empty-text="未找到订单。"
      @retry="loadOrder"
    >
      <div v-if="order" class="sm-stack">
        <section class="sm-card sm-order-head">
          <div class="sm-between">
            <div>
              <div class="sm-row">
                <ElTag size="small" effect="dark">{{ orderStatusLabel(order.status) }}</ElTag>
                <span v-if="order.is_synthetic" class="sm-synthetic-tag">合成数据</span>
              </div>
              <p class="sm-order-amount">
                <span class="sm-muted">实付</span>
                <strong class="sm-price">{{ formatMoney(order.total_cents, order.currency) }}</strong>
              </p>
              <p class="sm-muted">
                下单 {{ formatDateTime(order.placed_at) }}
                <template v-if="order.paid_at"> · 支付 {{ formatDateTime(order.paid_at) }}</template>
              </p>
            </div>
            <div class="sm-row-wrap sm-order-actions">
              <ElButton v-if="canPay" type="primary" :loading="acting" @click="pay">立即支付</ElButton>
              <ElButton v-if="canCancel" :loading="acting" @click="cancel">取消订单</ElButton>
              <ElButton v-if="canRefund" type="warning" plain @click="openRefund(null)">
                申请退款
              </ElButton>
            </div>
          </div>

          <ol v-if="order.status !== 'cancelled'" class="sm-steps">
            <li
              v-for="(step, index) in statusSteps"
              :key="step"
              class="sm-step"
              :class="{ 'sm-step-done': index <= currentStep, 'sm-step-current': index === currentStep }"
            >
              <span class="sm-step-dot" />
              <span class="sm-step-label">{{ orderStatusLabel(step) }}</span>
            </li>
          </ol>
          <ElAlert
            v-else
            type="info"
            :closable="false"
            show-icon
            title="订单已取消，库存已释放"
            class="sm-cancel-note"
          />
        </section>

        <section class="sm-card">
          <h3 class="sm-section-title">商品明细</h3>
          <ElTable :data="order.items" size="small">
            <ElTableColumn prop="title" label="商品" min-width="220" />
            <ElTableColumn label="单价" width="110">
              <template #default="{ row }">{{ formatMoney(row.unit_price_cents, order.currency) }}</template>
            </ElTableColumn>
            <ElTableColumn prop="quantity" label="数量" width="70" />
            <ElTableColumn label="小计" width="110">
              <template #default="{ row }">
                {{ formatMoney(row.unit_price_cents * row.quantity, order.currency) }}
              </template>
            </ElTableColumn>
            <ElTableColumn label="可退" width="70">
              <template #default="{ row }">
                <ElTag size="small" :type="row.is_returnable ? 'success' : 'info'" effect="plain">
                  {{ row.is_returnable ? '支持' : '不支持' }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="操作" width="100">
              <template #default="{ row }">
                <ElButton
                  v-if="canRefund"
                  size="small"
                  text
                  type="warning"
                  @click="openRefund(row.id)"
                >
                  单独退款
                </ElButton>
              </template>
            </ElTableColumn>
          </ElTable>
        </section>

        <section v-if="refunds.length" class="sm-card">
          <h3 class="sm-section-title">退款记录</h3>
          <ElTable :data="refunds" size="small">
            <ElTableColumn prop="refund_no" label="退款单号" min-width="150">
              <template #default="{ row }">
                <span class="sm-mono">{{ row.refund_no }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="范围" width="90">
              <template #default="{ row }">{{ row.scope === 'order' ? '整单' : '单件' }}</template>
            </ElTableColumn>
            <ElTableColumn label="金额" width="110">
              <template #default="{ row }">
                <span class="sm-price">{{ formatMoney(row.amount_cents, 'CNY') }}</span>
              </template>
            </ElTableColumn>
            <ElTableColumn label="状态" width="110">
              <template #default="{ row }">
                <ElTag size="small" :type="refundStatusTagType(row.status)">
                  {{ refundStatusLabel(row.status) }}
                </ElTag>
              </template>
            </ElTableColumn>
            <ElTableColumn label="原因" min-width="120">
              <template #default="{ row }">{{ returnReasonLabel(row.reason_code) }}</template>
            </ElTableColumn>
            <ElTableColumn label="审核说明" min-width="160">
              <template #default="{ row }">{{ row.review_note || '—' }}</template>
            </ElTableColumn>
          </ElTable>
        </section>

        <section class="sm-card">
          <div class="sm-between">
            <h3 class="sm-section-title">物流</h3>
            <ElButton
              v-if="!shipmentRequested"
              size="small"
              :loading="shipmentLoading"
              @click="loadShipment"
            >
              查看物流
            </ElButton>
          </div>
          <StateBlock
            :loading="shipmentLoading"
            :error="shipmentError"
            :empty="shipmentRequested && !shipmentLoading && !shipmentError && !shipment"
            empty-text="该订单暂无可查看的物流记录（可能还未发货）。"
            @retry="loadShipment"
          >
            <ShipmentTimeline v-if="shipment" :shipment="shipment" />
          </StateBlock>
        </section>

        <section v-if="canReturn" class="sm-card">
          <ReturnWizard :order-id="order.id" :items="order.items" />
        </section>
      </div>
    </StateBlock>

    <ElDialog v-model="refundDialog" title="申请退款" width="min(30rem, 94vw)">
      <div class="sm-stack">
        <p class="sm-muted">
          提交后由人工客服审核，通过后原路退回。整单退款会撤销整笔订单金额的支付。
        </p>
        <div>
          <p class="sm-muted">退款范围</p>
          <ElSelect v-model="refundForm.orderItemId" clearable placeholder="整单退款" style="width: 100%">
            <ElOption value="" label="整单退款" />
            <ElOption
              v-for="item in order?.items ?? []"
              :key="item.id"
              :value="item.id"
              :label="`仅退：${item.title}`"
            />
          </ElSelect>
        </div>
        <div>
          <p class="sm-muted">退款原因</p>
          <ElSelect v-model="refundForm.reason" style="width: 100%">
            <ElOption
              v-for="option in RETURN_REASON_OPTIONS"
              :key="option.value"
              :value="option.value"
              :label="option.label"
            />
          </ElSelect>
        </div>
        <div>
          <p class="sm-muted">补充说明（可选）</p>
          <ElInput
            v-model="refundForm.note"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="比如：临时改变计划 / 商品破损，已拍照"
          />
        </div>
      </div>
      <template #footer>
        <ElButton @click="refundDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="acting" @click="submitRefund">提交申请</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.sm-order-head {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sm-order-amount {
  margin: 8px 0 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.sm-order-amount strong {
  font-size: 26px;
}

.sm-order-actions {
  align-self: flex-start;
}

.sm-synthetic-tag {
  padding: 0 7px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}

.sm-steps {
  display: flex;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--sm-border);
  padding-top: 14px;
}

.sm-step {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
  color: var(--sm-text-tertiary);
  font-size: 12px;
}

.sm-step-dot {
  width: 100%;
  height: 4px;
  border-radius: 999px;
  background: var(--sm-border);
}

.sm-step-done {
  color: var(--sm-primary-dark);
}

.sm-step-done .sm-step-dot {
  background: var(--sm-primary);
}

.sm-step-current .sm-step-label {
  font-weight: 700;
}

.sm-cancel-note {
  margin-top: 4px;
}

.sm-section-title {
  margin: 0 0 10px;
  font-size: 15px;
}
</style>
