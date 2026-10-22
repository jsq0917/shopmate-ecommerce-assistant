<script setup lang="ts">
/**
 * 商品卡片网格。价格/库存/as_of 全部来自工具事实，不推断、不补写。
 * 卡片可直接加购（使用当前展示的规格快照），也可打开详情换规格。
 */

import { ElButton, ElCheckbox, ElTag } from 'element-plus'

import DataAsOfTag from '@/components/common/DataAsOfTag.vue'
import ProductThumb from '@/components/common/ProductThumb.vue'
import { useCart } from '@/composables/useCart'
import { attributeValueText, formatMoney, stockStatusLabel } from '@/utils/format'
import type { ProductCardBase } from '@/api/types'

defineProps<{
  cards: ProductCardBase[]
  selectable?: boolean
  selectedIds?: string[]
  /** 卡片右上角是否显示「可加购」入口。 */
  buyable?: boolean
}>()

const emit = defineEmits<{
  (e: 'detail', card: ProductCardBase): void
  (e: 'toggle-compare', productId: string): void
}>()

const cart = useCart()

/** 搜索卡片带 category；SSE 商品卡不带，退回空字符串使用默认封面。 */
function cardCategory(card: ProductCardBase): string {
  const category = (card as ProductCardBase & { category?: string }).category
  return category ?? ''
}

function stockClass(status: string): string {
  if (status === 'in_stock') return 'sm-stock-in'
  if (status === 'out_of_stock') return 'sm-stock-out'
  return 'sm-stock-unknown'
}

function addToCart(card: ProductCardBase): void {
  if (card.stock_status === 'out_of_stock') return
  cart.add({
    variantId: card.variant_id,
    productId: card.product_id,
    title: card.title,
    category: cardCategory(card),
    priceCents: card.price_cents,
    currency: card.currency,
    availableQty: card.available_qty,
  })
}
</script>

<template>
  <div class="sm-product-grid">
    <article v-for="card in cards" :key="card.variant_id" class="sm-product-card sm-card-hover">
      <div class="sm-product-cover">
        <ProductThumb :category="cardCategory(card)" :title="card.title" />
        <span v-if="card.is_synthetic" class="sm-synthetic-tag">合成</span>
        <span v-if="card.stock_status === 'out_of_stock'" class="sm-soldout">暂时无货</span>
      </div>

      <div class="sm-product-body">
        <h4 class="sm-product-title" :title="card.title">{{ card.title }}</h4>

        <div class="sm-product-meta">
          <span class="sm-product-price">{{ formatMoney(card.price_cents, card.currency) }}</span>
          <span class="sm-product-stock" :class="stockClass(card.stock_status)">
            {{ stockStatusLabel(card.stock_status) }}
            <template v-if="card.available_qty !== null"> · {{ card.available_qty }} 件</template>
            <template v-else> · 数量未知</template>
          </span>
        </div>

        <div v-if="Object.keys(card.attributes).length" class="sm-product-attrs">
          <span
            v-for="[key, value] in Object.entries(card.attributes).slice(0, 3)"
            :key="key"
            class="sm-attr-chip"
            :title="`${key}: ${attributeValueText(value)}`"
          >
            {{ attributeValueText(value) }}
          </span>
        </div>

        <div v-if="card.matched_reasons.length" class="sm-product-reasons">
          <ElTag v-for="reason in card.matched_reasons.slice(0, 3)" :key="reason" size="small" type="info" effect="plain">
            {{ reason }}
          </ElTag>
        </div>

        <footer class="sm-product-foot">
          <DataAsOfTag :as-of="card.as_of" />
          <div class="sm-row">
            <ElCheckbox
              v-if="selectable"
              :model-value="selectedIds?.includes(card.product_id) ?? false"
              @change="emit('toggle-compare', card.product_id)"
            >
              比较
            </ElCheckbox>
            <ElButton size="small" text @click="emit('detail', card)">详情</ElButton>
            <ElButton
              size="small"
              type="primary"
              :disabled="card.stock_status === 'out_of_stock' || buyable === false"
              @click="addToCart(card)"
            >
              加购
            </ElButton>
          </div>
        </footer>
      </div>
    </article>
  </div>
</template>

<style scoped>
.sm-product-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 14px;
  margin: 10px 0;
}

.sm-product-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--sm-border);
  border-radius: var(--sm-radius);
  background: var(--sm-surface);
  overflow: hidden;
  box-shadow: var(--sm-shadow-xs);
}

.sm-product-cover {
  position: relative;
  background: var(--sm-bg);
}

.sm-synthetic-tag {
  position: absolute;
  top: 8px;
  left: 8px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgb(255 255 255 / 86%);
  color: var(--sm-warning);
  font-size: 10px;
  font-weight: 600;
  backdrop-filter: blur(4px);
}

.sm-soldout {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgb(255 255 255 / 62%);
  color: var(--sm-text-secondary);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.08em;
}

.sm-product-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px 14px;
  flex: 1;
}

.sm-product-title {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  font-weight: 600;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 38px;
}

.sm-product-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 6px;
  flex-wrap: wrap;
}

.sm-product-price {
  font-size: 19px;
  font-weight: 750;
  color: var(--sm-accent);
  font-variant-numeric: tabular-nums;
}

.sm-product-stock {
  font-size: 11px;
}

.sm-stock-in {
  color: var(--sm-success);
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
  font-size: 11px;
  color: var(--sm-text-secondary);
}

.sm-product-reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.sm-product-foot {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  flex-wrap: wrap;
  padding-top: 4px;
}
</style>
