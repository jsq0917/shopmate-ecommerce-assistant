<script setup lang="ts">
/**
 * 工具执行状态列表。仅展示后端下发的受控中文文案，不展示内部异常。
 */

import type { TurnToolStatus } from '@/composables/useChatStream'

defineProps<{ statuses: TurnToolStatus[] }>()

const TOOL_LABELS: Record<string, string> = {
  search_products: '商品搜索',
  get_product_detail: '商品详情',
  compare_products: '商品比较',
  check_stock: '库存查询',
  get_promotion: '优惠查询',
  get_order_status: '订单查询',
  get_shipment: '物流查询',
  check_return_eligibility: '退货资格',
  create_return_request: '创建退货申请',
  create_handoff_ticket: '转人工工单',
}

function statusIcon(status: TurnToolStatus['status']): string {
  if (status === 'started') return '⏳'
  if (status === 'succeeded') return '✓'
  if (status === 'failed') return '✗'
  return '–'
}
</script>

<template>
  <ul v-if="statuses.length" class="sm-tool-status" aria-label="工具执行状态">
    <li v-for="(item, index) in statuses" :key="index" class="sm-tool-item" :class="`sm-tool-${item.status}`">
      <span class="sm-tool-icon" aria-hidden="true">{{ statusIcon(item.status) }}</span>
      <span class="sm-tool-name">{{ TOOL_LABELS[item.toolName] ?? item.toolName }}</span>
      <span class="sm-tool-message">{{ item.displayMessage ?? '' }}</span>
      <span v-if="item.errorCode" class="sm-tool-error">失败码：{{ item.errorCode }}</span>
    </li>
  </ul>
</template>

<style scoped>
.sm-tool-status {
  list-style: none;
  margin: 6px 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--sm-bg);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sm-tool-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
  color: var(--sm-text-secondary);
}

.sm-tool-icon {
  flex: none;
}

.sm-tool-name {
  font-weight: 600;
  color: var(--sm-text);
}

.sm-tool-failed .sm-tool-message {
  color: var(--sm-danger);
}

.sm-tool-error {
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
</style>
