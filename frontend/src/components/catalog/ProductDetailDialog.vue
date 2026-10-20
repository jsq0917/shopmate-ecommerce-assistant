<script setup lang="ts">
/**
 * 商品详情 / 库存对话框。数据来自 GET /products/{id}；未知字段显示“暂无数据”。
 */

import { ref, watch } from 'vue'
import { ElButton, ElDialog, ElTable, ElTableColumn, ElTag } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { productsApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { ProductDetailData } from '@/api/types'
import { attributeValueText, formatDateTime, formatMoney, stockStatusLabel } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  productId: string | null
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()

const loading = ref(false)
const error = ref<ApiError | null>(null)
const detail = ref<ProductDetailData | null>(null)

async function load(): Promise<void> {
  if (!props.productId) return
  loading.value = true
  error.value = null
  detail.value = null
  try {
    detail.value = await productsApi.detail(props.productId)
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
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="detail?.product.title ?? '商品详情'"
    width="min(46rem, 94vw)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <StateBlock :loading="loading" :error="error" :empty="!loading && !error && !detail">
      <template v-if="detail">
        <div class="sm-detail-head">
          <div>
            <h3 class="sm-detail-title">{{ detail.product.title }}</h3>
            <p class="sm-muted">
              {{ detail.product.brand ?? '品牌未知' }} · {{ detail.product.category }}
              <span v-if="detail.product.is_synthetic" class="sm-synthetic-tag">合成数据</span>
            </p>
          </div>
          <p class="sm-muted">数据时间：{{ formatDateTime(detail.as_of) }}</p>
        </div>

        <p v-if="detail.product.description" class="sm-detail-desc">{{ detail.product.description }}</p>

        <div v-if="Object.keys(detail.product.attributes).length" class="sm-row-wrap sm-detail-attrs">
          <ElTag v-for="(value, key) in detail.product.attributes" :key="key" size="small" effect="plain">
            {{ key }}：{{ attributeValueText(value) }}
          </ElTag>
        </div>

        <h4 class="sm-detail-subtitle">规格与库存</h4>
        <ElTable :data="detail.product.variants" size="small" border>
          <ElTableColumn prop="sku" label="SKU" min-width="120" />
          <ElTableColumn prop="title" label="规格" min-width="140" />
          <ElTableColumn label="价格" min-width="110">
            <template #default="{ row }">
              {{ formatMoney(row.price_cents, row.currency) }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="库存" min-width="150">
            <template #default="{ row }">
              {{ stockStatusLabel(row.stock_status) }}
              <span v-if="row.available_qty !== null" class="sm-muted">（{{ row.available_qty }} 件）</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="库存更新时间" min-width="150">
            <template #default="{ row }">
              {{ row.stock_updated_at ? formatDateTime(row.stock_updated_at) : '--' }}
            </template>
          </ElTableColumn>
        </ElTable>
      </template>
    </StateBlock>

    <template #footer>
      <ElButton @click="close">关闭</ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.sm-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.sm-detail-title {
  margin: 0 0 4px;
}

.sm-synthetic-tag {
  margin-left: 8px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}

.sm-detail-desc {
  color: var(--sm-text-secondary);
}

.sm-detail-attrs {
  margin-bottom: 8px;
}

.sm-detail-subtitle {
  margin: 12px 0 8px;
  font-size: 14px;
}
</style>
