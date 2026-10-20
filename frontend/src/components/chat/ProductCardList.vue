<script setup lang="ts">
/**
 * 商品卡片列表。价格/库存/as_of 全部来自工具事实，不推断、不补写。
 */

import { ElButton, ElCheckbox, ElTag } from 'element-plus'

import DataAsOfTag from '@/components/common/DataAsOfTag.vue'
import { attributeValueText, formatMoney, stockStatusLabel } from '@/utils/format'
import type { ProductCardBase } from '@/api/types'

defineProps<{
  cards: ProductCardBase[]
  selectable?: boolean
  selectedIds?: string[]
}>()

const emit = defineEmits<{
  (e: 'detail', card: ProductCardBase): void
  (e: 'toggle-compare', productId: string): void
}>()

function stockClass(status: string): string {
  if (status === 'in_stock') return 'sm-stock-in'
  if (status === 'out_of_stock') return 'sm-stock-out'
  return 'sm-stock-unknown'
}
</script>

<template>
  <div class="sm-product-grid">
    <article v-for="card in cards" :key="card.variant_id" class="sm-product-card">
      <header class="sm-product-head">
        <h4 class="sm-product-title" :title="card.title">{{ card.title }}</h4>
        <span v-if="card.is_synthetic" class="sm-synthetic-tag">合成</span>
      </header>

      <p class="sm-product-price">{{ formatMoney(card.price_cents, card.currency) }}</p>

      <p class="sm-product-stock" :class="stockClass(card.stock_status)">
        {{ stockStatusLabel(card.stock_status) }}
        <span v-if="card.available_qty !== null" class="sm-muted"> · 可售 {{ card.available_qty }} 件</span>
        <span v-else class="sm-muted"> · 数量未知</span>
      </p>

      <div v-if="card.matched_reasons.length" class="sm-row-wrap">
        <ElTag v-for="reason in card.matched_reasons" :key="reason" size="small" type="info" effect="plain">
          {{ reason }}
        </ElTag>
      </div>

      <div v-if="Object.keys(card.attributes).length" class="sm-product-attrs">
        <span
          v-for="(value, key) in card.attributes"
          :key="key"
          class="sm-attr-chip"
          :title="`${key}: ${attributeValueText(value)}`"
        >
          {{ attributeValueText(value) }}
        </span>
      </div>

      <footer class="sm-product-foot">
        <DataAsOfTag :as-of="card.as_of" />
        <span class="sm-row">
          <ElButton size="small" text type="primary" @click="emit('detail', card)">详情/库存</ElButton>
          <ElCheckbox
            v-if="selectable"
            :model-value="selectedIds?.includes(card.product_id) ?? false"
            @change="emit('toggle-compare', card.product_id)"
          >
            比较
          </ElCheckbox>
        </span>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.sm-product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
  margin: 8px 0;
}

.sm-product-card {
  border: 1px solid var(--sm-border);
  border-radius: var(--sm-radius);
  background: var(--sm-surface);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sm-product-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.sm-product-title {
  margin: 0;
  font-size: 14px;
  line-height: 1.4;
}

.sm-synthetic-tag {
  flex: none;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}

.sm-product-price {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--sm-danger);
}

.sm-product-stock {
  margin: 0;
  font-size: 12px;
}

.sm-stock-in {
  color: var(--sm-primary-dark);
}

.sm-stock-out {
  color: var(--sm-danger);
}

.sm-stock-unknown {
  color: var(--sm-text-secondary);
}

.sm-product-attrs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.sm-attr-chip {
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--sm-bg);
  border: 1px solid var(--sm-border);
  font-size: 12px;
  color: var(--sm-text-secondary);
}

.sm-product-foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
