<script setup lang="ts">
/**
 * 商品详情：封面、卖点、规格选择、加入购物车/立即购买。
 * 价格与库存来自 GET /products/{id}，未知字段显示“暂无数据”，不做推测。
 */

import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElDialog, ElInputNumber, ElMessage, ElTag } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import ProductThumb from '@/components/common/ProductThumb.vue'
import { productsApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { ProductDetailData, VariantDetailItem } from '@/api/types'
import { useCart } from '@/composables/useCart'
import { attributeValueText, formatDateTime, formatMoney, stockStatusLabel } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  productId: string | null
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const router = useRouter()
const cart = useCart()

const loading = ref(false)
const error = ref<ApiError | null>(null)
const detail = ref<ProductDetailData | null>(null)
const selectedVariantId = ref<string | null>(null)
const quantity = ref(1)

const variants = computed(() => detail.value?.product.variants ?? [])
const selectedVariant = computed(
  () => variants.value.find((variant) => variant.id === selectedVariantId.value) ?? null,
)
const soldOut = computed(() => selectedVariant.value?.stock_status === 'out_of_stock')
const maxQuantity = computed(() => {
  const available = selectedVariant.value?.available_qty
  if (available === null || available === undefined) return 99
  return Math.max(1, Math.min(available, 99))
})
const priceRange = computed(() => {
  if (!variants.value.length) return '--'
  const prices = variants.value.map((variant) => variant.price_cents)
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  return min === max
    ? formatMoney(min, 'CNY')
    : `${formatMoney(min, 'CNY')} - ${formatMoney(max, 'CNY')}`
})

async function load(): Promise<void> {
  if (!props.productId) return
  loading.value = true
  error.value = null
  detail.value = null
  try {
    detail.value = await productsApi.detail(props.productId)
    const firstAvailable = variants.value.find((variant) => variant.stock_status !== 'out_of_stock')
    selectedVariantId.value = (firstAvailable ?? variants.value[0])?.id ?? null
    quantity.value = 1
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.productId],
  ([visible]) => {
    if (visible) void load()
  },
  { immediate: true },
)

function close(): void {
  emit('update:modelValue', false)
}

function addToCart(goCheckout: boolean): void {
  if (!detail.value || !selectedVariant.value) return
  if (soldOut.value) {
    ElMessage.warning('该规格暂时无货，换个规格看看')
    return
  }
  const variant: VariantDetailItem = selectedVariant.value
  cart.add(
    {
      variantId: variant.id,
      productId: detail.value.product.id,
      title: variant.title,
      category: detail.value.product.category,
      priceCents: variant.price_cents,
      currency: variant.currency,
      availableQty: variant.available_qty,
    },
    quantity.value,
  )
  if (goCheckout) {
    close()
    void router.push('/checkout')
    return
  }
  ElMessage.success('已加入购物车')
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="detail?.product.title ?? '商品详情'"
    width="min(52rem, 94vw)"
    class="sm-detail-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <StateBlock :loading="loading" :error="error" :empty="!loading && !error && !detail">
      <template v-if="detail">
        <div class="sm-detail-top">
          <ProductThumb
            :category="detail.product.category"
            :title="detail.product.title"
            :image-url="detail.product.image_url"
            size="lg"
            class="sm-detail-cover"
          />
          <div class="sm-detail-info">
            <div class="sm-row-wrap">
              <ElTag size="small" effect="plain">{{ detail.product.category }}</ElTag>
              <span class="sm-muted">{{ detail.product.brand ?? '品牌未知' }}</span>
              <span v-if="detail.product.is_synthetic" class="sm-synthetic-tag">合成数据</span>
            </div>
            <p class="sm-detail-price">{{ priceRange }}</p>
            <p class="sm-detail-desc">{{ detail.product.description }}</p>
            <div v-if="Object.keys(detail.product.attributes).length" class="sm-row-wrap">
              <span
                v-for="(value, key) in detail.product.attributes"
                :key="key"
                class="sm-attr-chip"
                :title="String(key)"
              >
                {{ attributeValueText(value) }}
              </span>
            </div>
            <p class="sm-muted">数据时间：{{ formatDateTime(detail.as_of) }}</p>
          </div>
        </div>

        <h4 class="sm-detail-subtitle">选择规格</h4>
        <div class="sm-variant-grid">
          <button
            v-for="variant in variants"
            :key="variant.id"
            type="button"
            class="sm-variant"
            :class="{
              'sm-variant-active': variant.id === selectedVariantId,
              'sm-variant-disabled': variant.stock_status === 'out_of_stock',
            }"
            @click="selectedVariantId = variant.id"
          >
            <span class="sm-variant-title">{{ variant.title.split('·').pop()?.trim() || variant.title }}</span>
            <span class="sm-variant-price">{{ formatMoney(variant.price_cents, variant.currency) }}</span>
            <span class="sm-variant-stock">
              {{ stockStatusLabel(variant.stock_status) }}
              <template v-if="variant.available_qty !== null"> · {{ variant.available_qty }} 件</template>
            </span>
          </button>
        </div>

        <div class="sm-buy-row">
          <span class="sm-muted">数量</span>
          <ElInputNumber v-model="quantity" :min="1" :max="maxQuantity" size="small" />
          <span v-if="selectedVariant?.available_qty !== null" class="sm-muted">
            最多可购 {{ selectedVariant?.available_qty ?? 0 }} 件
          </span>
        </div>
      </template>
    </StateBlock>

    <template #footer>
      <ElButton @click="close">关闭</ElButton>
      <ElButton :disabled="soldOut || !selectedVariant" @click="addToCart(false)">加入购物车</ElButton>
      <ElButton type="primary" :disabled="soldOut || !selectedVariant" @click="addToCart(true)">
        立即购买
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.sm-detail-top {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 18px;
}

.sm-detail-cover {
  align-self: start;
}

.sm-detail-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sm-detail-price {
  margin: 0;
  font-size: 26px;
  font-weight: 750;
  color: var(--sm-accent);
  font-variant-numeric: tabular-nums;
}

.sm-detail-desc {
  margin: 0;
  color: var(--sm-text-secondary);
  font-size: 13px;
}

.sm-detail-subtitle {
  margin: 16px 0 8px;
  font-size: 14px;
}

.sm-synthetic-tag {
  padding: 0 7px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}

.sm-attr-chip {
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--sm-bg);
  border: 1px solid var(--sm-border);
  font-size: 12px;
  color: var(--sm-text-secondary);
}

.sm-variant-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 8px;
}

.sm-variant {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: var(--sm-radius-sm);
  border: 1.5px solid var(--sm-border);
  background: var(--sm-surface);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.sm-variant:hover {
  border-color: var(--sm-primary);
}

.sm-variant-active {
  border-color: var(--sm-primary);
  background: var(--sm-primary-soft);
}

.sm-variant-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sm-variant-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--sm-text);
}

.sm-variant-price {
  font-size: 13px;
  color: var(--sm-accent);
  font-weight: 650;
}

.sm-variant-stock {
  font-size: 11px;
  color: var(--sm-text-secondary);
}

.sm-buy-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}

@media (max-width: 720px) {
  .sm-detail-top {
    grid-template-columns: 1fr;
  }
}
</style>
