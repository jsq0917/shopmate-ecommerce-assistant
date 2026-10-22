<script setup lang="ts">
/**
 * 我的退款：只展示当前账号自己的申请，状态由客服审核推进。
 * 退款是「申请 → 人工审核 → 原路退回」，页面不承诺到账时间。
 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElTable, ElTableColumn, ElTag } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { refundsApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { RefundItem } from '@/api/types'
import {
  formatDateTime,
  formatMoney,
  refundStatusLabel,
  refundStatusTagType,
  returnReasonLabel,
} from '@/utils/format'

const router = useRouter()
const loading = ref(true)
const error = ref<ApiError | null>(null)
const rows = ref<RefundItem[]>([])

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const data = await refundsApi.list({ limit: 50 })
    rows.value = data.items
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="sm-page">
    <div class="sm-page-header">
      <div>
        <h2 class="sm-page-title">我的退款</h2>
        <p class="sm-page-subtitle">退款提交后由人工客服审核，通过后原路退回（演示环境不产生真实资金流）。</p>
      </div>
      <ElButton @click="router.push('/orders')">我的订单</ElButton>
    </div>

    <StateBlock
      :loading="loading"
      :error="error"
      :empty="!loading && !error && rows.length === 0"
      empty-text="还没有退款申请。可以在订单详情里点「申请退款」。"
      @retry="load"
    >
      <div class="sm-card">
        <ElTable :data="rows" style="width: 100%">
          <ElTableColumn prop="refund_no" label="退款单号" min-width="150">
            <template #default="{ row }">
              <span class="sm-mono">{{ row.refund_no }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn prop="order_no" label="订单号" min-width="140">
            <template #default="{ row }">
              <router-link :to="`/orders/${row.order_id}`">{{ row.order_no }}</router-link>
            </template>
          </ElTableColumn>
          <ElTableColumn label="金额" width="110">
            <template #default="{ row }">
              <span class="sm-price">{{ formatMoney(row.amount_cents, 'CNY') }}</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="原因" min-width="120">
            <template #default="{ row }">{{ returnReasonLabel(row.reason_code) }}</template>
          </ElTableColumn>
          <ElTableColumn label="状态" width="120">
            <template #default="{ row }">
              <ElTag size="small" :type="refundStatusTagType(row.status)" effect="light">
                {{ refundStatusLabel(row.status) }}
              </ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="申请时间" min-width="160">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </ElTableColumn>
          <ElTableColumn label="审核说明" min-width="200">
            <template #default="{ row }">
              <span class="sm-muted">{{ row.review_note || '—' }}</span>
            </template>
          </ElTableColumn>
        </ElTable>
      </div>
    </StateBlock>
  </div>
</template>
