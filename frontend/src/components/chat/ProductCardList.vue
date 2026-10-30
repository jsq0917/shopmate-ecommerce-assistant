<script setup lang="ts">
/**
 * 商品卡片网格。价格/库存/as_of 全部来自工具事实，不推断、不补写。
 * 卡片可直接加购：默认用卡片上的规格快照；聊天场景（revalidate）会先向商品详情接口复核
 * 一次库存与价格，复核到售罄就拒绝加入。也可打开详情换规格。
 */

import { onBeforeUnmount, reactive } from 'vue'
import { ElButton, ElCheckbox, ElMessage, ElTag } from 'element-plus'

import DataAsOfTag from '@/components/common/DataAsOfTag.vue'
import ProductThumb from '@/components/common/ProductThumb.vue'
import { productsApi } from '@/api/endpoints'
import { useCart } from '@/composables/useCart'
import { attributeValueText, formatMoney, stockStatusLabel } from '@/utils/format'
import type { ProductCardBase } from '@/api/types'

/**
 * `buyable` 必须显式给默认值：仅声明 `buyable?: boolean` 时 Vue 会把「未传」的布尔 prop
 * 强制转成 false，按钮就会恒定 disabled（这正是之前「加购」点不动的根因）。
 */
const props = withDefaults(
  defineProps<{
    cards: ProductCardBase[]
    selectable?: boolean
    selectedIds?: string[]
    /** 卡片右上角是否显示「可加购」入口。 */
    buyable?: boolean
    /**
     * 加购前是否用商品详情接口复核库存。
     * 聊天里的卡片是历史快照（可能几分钟前），需要复核；商品中心列表本身就是刚查到的，不必再打一次。
     */
    revalidate?: boolean
  }>(),
  { buyable: true, selectable: false, selectedIds: () => [], revalidate: false },
)

const emit = defineEmits<{
  (e: 'detail', card: ProductCardBase): void
  (e: 'toggle-compare', productId: string): void
}>()

const cart = useCart()

/** 正在复核/写入的规格：既用于按钮 loading，也是重复点击的闸门（同一规格只允许一个在途请求）。 */
const pendingVariants = reactive(new Set<string>())
/** 刚加购成功的规格：按钮短暂显示「已加入」，给出即时反馈。 */
const addedVariants = reactive(new Set<string>())
const flashTimers = new Map<string, number>()
const FLASH_MS = 1400

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

function isPending(card: ProductCardBase): boolean {
  return pendingVariants.has(card.variant_id)
}

function buttonLabel(card: ProductCardBase): string {
  if (isPending(card)) return '加购中'
  if (addedVariants.has(card.variant_id)) return '已加入'
  return '加购'
}

function flashAdded(variantId: string): void {
  addedVariants.add(variantId)
  const existing = flashTimers.get(variantId)
  if (existing) window.clearTimeout(existing)
  flashTimers.set(
    variantId,
    window.setTimeout(() => {
      addedVariants.delete(variantId)
      flashTimers.delete(variantId)
    }, FLASH_MS),
  )
}

onBeforeUnmount(() => {
  for (const timer of flashTimers.values()) window.clearTimeout(timer)
  flashTimers.clear()
})

/**
 * 加购：卡片快照 → （可选）服务端库存复核 → 写入本地购物车 → 反馈。
 *
 * 库存/价格只能来自结构化数据（业务铁律 1）：复核到售罄就拒绝加入，
 * 复核接口不可用时退回卡片快照并在提示里说明「结算会重新校验」，不阻断用户。
 */
async function addToCart(card: ProductCardBase): Promise<void> {
  if (!props.buyable) return
  if (card.stock_status === 'out_of_stock') {
    ElMessage.warning('该规格暂时无货，换个规格看看')
    return
  }
  if (pendingVariants.has(card.variant_id)) return
  pendingVariants.add(card.variant_id)

  try {
    let priceCents = card.price_cents
    let currency = card.currency
    let availableQty = card.available_qty
    let revalidated = true

    if (props.revalidate) {
      try {
        const detail = await productsApi.detail(card.product_id)
        const variant = detail.product.variants.find((row) => row.id === card.variant_id)
        if (!variant) {
          ElMessage.warning('该规格已下架，打开「详情」换个规格看看')
          return
        }
        if (variant.stock_status === 'out_of_stock' || (variant.available_qty ?? 1) <= 0) {
          ElMessage.warning('该规格刚刚售罄，换个规格或稍后再试')
          return
        }
        priceCents = variant.price_cents
        currency = variant.currency
        availableQty = variant.available_qty
      } catch {
        revalidated = false
      }
    }

    const result = cart.add({
      variantId: card.variant_id,
      productId: card.product_id,
      title: card.title,
      category: cardCategory(card),
      priceCents,
      currency,
      availableQty,
    })

    if (result.quantity === 0) {
      ElMessage.warning('该规格暂无可售库存，未能加入购物车')
      return
    }
    flashAdded(card.variant_id)
    if (!revalidated) {
      ElMessage.warning('库存校验失败，已按卡片显示的信息加入，结算时会重新校验')
    } else if (result.added === 0) {
      ElMessage.warning(`该规格最多可买 ${result.quantity} 件，购物车数量未再增加`)
    } else if (result.capped) {
      ElMessage.success(`已加入购物车（受可售库存限制，当前共 ${result.quantity} 件）`)
    } else {
      ElMessage.success(`已加入购物车（共 ${result.quantity} 件）`)
    }
  } finally {
    pendingVariants.delete(card.variant_id)
  }
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
              :loading="isPending(card)"
              :disabled="card.stock_status === 'out_of_stock' || !buyable"
              @click="addToCart(card)"
            >
              {{ buttonLabel(card) }}
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
