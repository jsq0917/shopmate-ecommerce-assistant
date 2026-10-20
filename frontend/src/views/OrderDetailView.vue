<script setup lang="ts">
/**
 * 订单详情：订单信息 + 物流（按需加载）+ 退货向导。
 */

import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElButton, ElTable, ElTableColumn, ElTag } from 'element-plus'

import ReturnWizard from '@/components/orders/ReturnWizard.vue'
import ShipmentTimeline from '@/components/orders/ShipmentTimeline.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { ordersApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { OrderDetailData, ShipmentData } from '@/api/types'
import { formatDateTime, formatMoney, orderStatusLabel } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const orderId = String(route.params.orderId ?? '')

const loading = ref(true)
const error = ref<ApiError | null>(null)
const order = ref<OrderDetailData | null>(null)

const shipment = ref<ShipmentData | null>(null)
const shipmentLoading = ref(false)
const shipmentError = ref<ApiError | null>(null)
const shipmentRequested = ref(false)

async function loadOrder(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    order.value = await ordersApi.detail(orderId)
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

onMounted(loadOrder)
</script>

<template>
  <div class="sm-page">
    <div class="sm-between">
      <h2 class="sm-page-title">订单详情</h2>
      <ElButton size="small" @click="router.push('/orders')">返回订单列表</ElButton>
    </div>

    <StateBlock :loading="loading && !order" :error="error" :empty="!loading && !error && !order" empty-text="未找到订单。" @retry="loadOrder">
      <template v-if="order">
        <div class="sm-card sm-order-head">
          <div>
            <p class="sm-order-no">订单号：<span class="sm-mono">{{ order.order_no }}</span></p>
            <p class="sm-muted">
              状态：<ElTag size="small">{{ orderStatusLabel(order.status) }}</ElTag>
              · 下单时间 {{ formatDateTime(order.placed_at) }} · 状态更新 {{ formatDateTime(order.status_updated_at) }}
              · 合计 {{ formatMoney(order.total_cents, order.currency) }}
              <span v-if="order.is_synthetic" class="sm-synthetic-tag">合成数据</span>
            </p>
          </div>
        </div>

        <div class="sm-card">
          <h3 class="sm-section-title">商品明细</h3>
          <ElTable :data="order.items" size="small" border>
            <ElTableColumn prop="sku" label="SKU" min-width="130" />
            <ElTableColumn prop="title" label="商品" min-width="160" />
            <ElTableColumn prop="quantity" label="数量" width="80" />
            <ElTableColumn label="单价" min-width="110">
              <template #default="{ row }">{{ formatMoney(row.unit_price_cents, order.currency) }}</template>
            </ElTableColumn>
            <ElTableColumn prop="status" label="状态" min-width="100" />
          </ElTable>
        </div>

        <div class="sm-card">
          <div class="sm-between">
            <h3 class="sm-section-title">物流</h3>
            <ElButton v-if="!shipmentRequested" size="small" type="primary" :loading="shipmentLoading" @click="loadShipment">
              查看物流
            </ElButton>
          </div>
          <StateBlock
            :loading="shipmentLoading"
            :error="shipmentError"
            :empty="shipmentRequested && !shipmentLoading && !shipmentError && !shipment"
            empty-text="该订单暂无可查看的物流记录。"
            @retry="loadShipment"
          >
            <ShipmentTimeline v-if="shipment" :shipment="shipment" />
          </StateBlock>
        </div>

        <div class="sm-card">
          <ReturnWizard :order-id="order.id" :items="order.items" />
        </div>
      </template>
    </StateBlock>
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0;
  font-size: 18px;
}

.sm-order-head {
  margin: 12px 0;
}

.sm-order-no {
  margin: 0 0 4px;
  font-weight: 700;
}

.sm-section-title {
  margin: 0 0 10px;
  font-size: 15px;
}

.sm-synthetic-tag {
  margin-left: 8px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}

.sm-card {
  margin-bottom: 12px;
}
</style>
