<script setup lang="ts">
/**
 * 商品中心：受控搜索、商品卡片、2-4 件商品比较、详情/库存。
 * 预算单位为分（300 元 = 30000 分），输入框旁边提供元换算提示。
 */

import { computed, reactive, ref } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElForm, ElFormItem, ElInput, ElMessage, ElOption, ElSelect } from 'element-plus'

import ProductCardList from '@/components/chat/ProductCardList.vue'
import ProductCompareTable from '@/components/catalog/ProductCompareTable.vue'
import ProductDetailDialog from '@/components/catalog/ProductDetailDialog.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { productsApi } from '@/api/endpoints'
import { ApiError, toApiError } from '@/api/errors'
import type { CompareData, ProductCardBase, ProductSearchData } from '@/api/types'

const filters = reactive({
  q: '',
  category: '',
  brand: '',
  budgetMaxYuan: '',
  inStockOnly: false,
  limit: 10,
})

const loading = ref(false)
const error = ref<ApiError | null>(null)
const searched = ref(false)
const result = ref<ProductSearchData | null>(null)
const selected = ref<string[]>([])
const compareData = ref<CompareData | null>(null)
const compareError = ref<ApiError | null>(null)
const compareLoading = ref(false)
const detailVisible = ref(false)
const detailProductId = ref<string | null>(null)

const cards = computed(() => result.value?.items ?? [])
const budgetMaxCents = computed(() => {
  const yuan = Number(filters.budgetMaxYuan)
  if (!filters.budgetMaxYuan.trim() || !Number.isFinite(yuan) || yuan <= 0) return undefined
  return Math.round(yuan * 100)
})

async function search(): Promise<void> {
  // 商品搜索接口要求关键词非空（q 必填）；空关键词不发请求，给出明确提示。
  if (!filters.q.trim()) {
    ElMessage.warning('请输入搜索关键词后再搜索。')
    return
  }
  loading.value = true
  error.value = null
  try {
    result.value = await productsApi.search({
      q: filters.q.trim() || undefined,
      category: filters.category.trim() || undefined,
      brand: filters.brand.trim() || undefined,
      budget_max_cents: budgetMaxCents.value,
      in_stock_only: filters.inStockOnly,
      limit: filters.limit,
    })
    searched.value = true
    selected.value = []
    compareData.value = null
  } catch (caught) {
    error.value = toApiError(caught)
    result.value = null
  } finally {
    loading.value = false
  }
}

function toggleCompare(productId: string): void {
  if (selected.value.includes(productId)) {
    selected.value = selected.value.filter((id) => id !== productId)
    return
  }
  if (selected.value.length >= 4) {
    compareError.value = new ApiError({
      code: 'VALIDATION_ERROR',
      message: '最多同时比较 4 件商品，请先取消部分选择。',
      status: 400,
    })
    return
  }
  selected.value = [...selected.value, productId]
}

async function runCompare(): Promise<void> {
  if (selected.value.length < 2) return
  compareLoading.value = true
  compareError.value = null
  try {
    compareData.value = await productsApi.compare({ product_ids: selected.value })
  } catch (caught) {
    compareError.value = toApiError(caught)
    compareData.value = null
  } finally {
    compareLoading.value = false
  }
}

function openDetail(card: ProductCardBase): void {
  detailProductId.value = card.product_id
  detailVisible.value = true
}
</script>

<template>
  <div class="sm-page">
    <h2 class="sm-page-title">商品中心</h2>
    <p class="sm-muted">价格、库存与数据时间均来自结构化数据源；比较中缺失字段显示 unknown，不做推测。</p>

    <div class="sm-card sm-filters">
      <ElForm inline @submit.prevent="search">
        <ElFormItem label="关键词">
          <ElInput v-model="filters.q" placeholder="如：降噪耳机" clearable style="width: 10rem" />
        </ElFormItem>
        <ElFormItem label="类目">
          <ElInput v-model="filters.category" placeholder="如：耳机" clearable style="width: 8rem" />
        </ElFormItem>
        <ElFormItem label="品牌">
          <ElInput v-model="filters.brand" placeholder="如：SoundCore" clearable style="width: 8rem" />
        </ElFormItem>
        <ElFormItem label="预算上限（元）">
          <ElInput v-model="filters.budgetMaxYuan" placeholder="如：300" clearable style="width: 7rem" />
        </ElFormItem>
        <ElFormItem label="仅看有货">
          <ElCheckbox v-model="filters.inStockOnly" />
        </ElFormItem>
        <ElFormItem label="数量">
          <ElSelect v-model="filters.limit" style="width: 6rem">
            <ElOption :value="5" label="5" />
            <ElOption :value="10" label="10" />
            <ElOption :value="20" label="20" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" :loading="loading" @click="search">搜索</ElButton>
        </ElFormItem>
      </ElForm>
    </div>

    <div v-if="selected.length" class="sm-card sm-compare-bar">
      <span>已选 {{ selected.length }} 件（2-4 件可比较）</span>
      <ElButton size="small" type="primary" :disabled="selected.length < 2" :loading="compareLoading" @click="runCompare">
        开始比较
      </ElButton>
    </div>

    <ElAlert v-if="compareError" type="error" :closable="false" show-icon :title="compareError.message" class="sm-alert" />

    <StateBlock
      :loading="loading && !result"
      :error="error"
      :empty="!loading && !error && cards.length === 0"
      :empty-text="searched ? '没有符合条件的商品，试试其他关键词或放宽筛选。' : '输入关键词（如“降噪耳机”）后点击搜索；价格、库存与数据时间均来自结构化数据。'"
    >
      <ProductCardList
        v-if="cards.length"
        :cards="cards"
        selectable
        :selected-ids="selected"
        @detail="openDetail"
        @toggle-compare="toggleCompare"
      />
    </StateBlock>

    <div v-if="compareData" class="sm-card">
      <ProductCompareTable :data="compareData" />
    </div>

    <ProductDetailDialog v-model="detailVisible" :product-id="detailProductId" />
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0 0 4px;
  font-size: 18px;
}

.sm-filters {
  margin: 12px 0;
}

.sm-compare-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.sm-alert {
  margin-bottom: 12px;
}
</style>
