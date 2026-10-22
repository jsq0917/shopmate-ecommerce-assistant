<script setup lang="ts">
/**
 * 商品中心：默认展示在售商品，支持关键词搜索、预算/库存筛选、排序与 2-4 件比较。
 * 预算单位为元，提交时换算成后端要求的「分」。
 */

import { computed, onMounted, reactive, ref } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElEmpty, ElInput, ElOption, ElSelect } from 'element-plus'

import ProductCardList from '@/components/chat/ProductCardList.vue'
import ProductCompareTable from '@/components/catalog/ProductCompareTable.vue'
import ProductDetailDialog from '@/components/catalog/ProductDetailDialog.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { productsApi } from '@/api/endpoints'
import { ApiError, toApiError } from '@/api/errors'
import type { CompareData, ProductCardBase, ProductSearchData } from '@/api/types'

const QUICK_TAGS: Array<{ label: string; q: string }> = [
  { label: '降噪耳机', q: '降噪耳机' },
  { label: '机械键盘', q: '机械键盘' },
  { label: '跑鞋', q: '跑步鞋' },
  { label: '保温杯', q: '保温杯' },
  { label: '空气炸锅', q: '空气炸锅' },
  { label: '电动牙刷', q: '电动牙刷' },
  { label: '显示器', q: '显示器' },
  { label: '猫粮', q: '猫粮' },
  { label: '坚果', q: '坚果' },
]

const filters = reactive({
  q: '',
  budgetMaxYuan: '',
  inStockOnly: false,
  sort: 'relevance' as 'relevance' | 'price-asc' | 'price-desc',
  limit: 24,
})

const loading = ref(false)
const error = ref<ApiError | null>(null)
const result = ref<ProductSearchData | null>(null)
const searched = ref(false)
const activeTag = ref('')
const selected = ref<string[]>([])
const compareData = ref<CompareData | null>(null)
const compareError = ref<ApiError | null>(null)
const compareLoading = ref(false)
const detailVisible = ref(false)
const detailProductId = ref<string | null>(null)

const budgetMaxCents = computed(() => {
  const yuan = Number(filters.budgetMaxYuan)
  if (!filters.budgetMaxYuan.trim() || !Number.isFinite(yuan) || yuan <= 0) return undefined
  return Math.round(yuan * 100)
})

const cards = computed<ProductCardBase[]>(() => {
  const items = [...(result.value?.items ?? [])]
  if (filters.sort === 'price-asc') items.sort((a, b) => a.price_cents - b.price_cents)
  if (filters.sort === 'price-desc') items.sort((a, b) => b.price_cents - a.price_cents)
  return items
})

const resultCount = computed(() => result.value?.items.length ?? 0)

async function loadFeatured(): Promise<void> {
  loading.value = true
  error.value = null
  searched.value = false
  activeTag.value = ''
  try {
    result.value = await productsApi.featured({ limit: filters.limit })
  } catch (caught) {
    error.value = toApiError(caught)
    result.value = null
  } finally {
    loading.value = false
  }
}

async function search(keyword?: string): Promise<void> {
  const q = (keyword ?? filters.q).trim()
  if (!q) {
    await loadFeatured()
    return
  }
  filters.q = q
  loading.value = true
  error.value = null
  try {
    result.value = await productsApi.search({
      q,
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

async function pickTag(tag: { label: string; q: string }): Promise<void> {
  activeTag.value = tag.label
  filters.budgetMaxYuan = ''
  filters.inStockOnly = false
  await search(tag.q)
}

function resetFilters(): void {
  filters.budgetMaxYuan = ''
  filters.inStockOnly = false
  filters.sort = 'relevance'
  void loadFeatured()
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

onMounted(loadFeatured)
</script>

<template>
  <div class="sm-page">
    <section class="sm-hero">
      <div class="sm-hero-copy">
        <span class="sm-hero-eyebrow">SHOPMATE 精选</span>
        <h2 class="sm-hero-title">挑一件真正合适的</h2>
        <p class="sm-hero-sub">价格与库存实时来自商品系统，问客服还能帮你按预算挑选、横向对比。</p>
        <div class="sm-hero-search">
          <ElInput
            v-model="filters.q"
            size="large"
            placeholder="搜索商品，例如：降噪耳机 / 跑鞋 / 咖啡"
            clearable
            @keyup.enter="search()"
          />
          <ElButton type="primary" size="large" :loading="loading" @click="search()">搜索</ElButton>
        </div>
        <div class="sm-hero-tags">
          <button
            v-for="tag in QUICK_TAGS"
            :key="tag.label"
            type="button"
            class="sm-hero-tag"
            :class="{ 'sm-hero-tag-active': activeTag === tag.label }"
            @click="pickTag(tag)"
          >
            {{ tag.label }}
          </button>
        </div>
      </div>
      <div class="sm-hero-art" aria-hidden="true">
        <span>🎧</span><span>👟</span><span>☕</span><span>💡</span>
      </div>
    </section>

    <div class="sm-toolbar sm-card">
      <div class="sm-toolbar-group">
        <span class="sm-muted">预算上限（元）</span>
        <ElInput v-model="filters.budgetMaxYuan" placeholder="如 300" style="width: 7rem" clearable />
        <ElCheckbox v-model="filters.inStockOnly">仅看有货</ElCheckbox>
        <ElButton size="small" type="primary" plain :disabled="!filters.q.trim()" @click="search()">
          应用筛选
        </ElButton>
        <ElButton size="small" text @click="resetFilters">重置</ElButton>
      </div>
      <div class="sm-toolbar-group">
        <span class="sm-muted">排序</span>
        <ElSelect v-model="filters.sort" size="small" style="width: 8.5rem">
          <ElOption value="relevance" label="默认排序" />
          <ElOption value="price-asc" label="价格从低到高" />
          <ElOption value="price-desc" label="价格从高到低" />
        </ElSelect>
        <span class="sm-muted">{{ resultCount }} 件</span>
      </div>
    </div>

    <div v-if="selected.length" class="sm-compare-bar sm-card">
      <span>已选 {{ selected.length }} 件（2-4 件可比较）</span>
      <div class="sm-row">
        <ElButton size="small" text @click="selected = []">清空</ElButton>
        <ElButton
          size="small"
          type="primary"
          :disabled="selected.length < 2"
          :loading="compareLoading"
          @click="runCompare"
        >
          开始比较
        </ElButton>
      </div>
    </div>

    <ElAlert
      v-if="compareError"
      type="error"
      :closable="false"
      show-icon
      :title="compareError.message"
      class="sm-block"
    />

    <StateBlock
      :loading="loading && !result"
      :error="error"
      :empty="!loading && !error && cards.length === 0"
      :empty-text="searched ? '没有符合条件的商品，换个关键词或放宽预算试试。' : '暂无在售商品。'"
      @retry="loadFeatured"
    >
      <div v-if="!searched && !loading" class="sm-section-head">
        <h3 class="sm-section-title">在售精选</h3>
        <span class="sm-muted">按价格从低到高展示前 {{ resultCount }} 件</span>
      </div>
      <ProductCardList
        v-if="cards.length"
        :cards="cards"
        selectable
        :selected-ids="selected"
        @detail="openDetail"
        @toggle-compare="toggleCompare"
      />
    </StateBlock>

    <div v-if="compareData" class="sm-card sm-compare-wrap">
      <ProductCompareTable :data="compareData" />
    </div>

    <ElEmpty v-if="!loading && !error && !cards.length" description=" " />

    <ProductDetailDialog v-model="detailVisible" :product-id="detailProductId" />
  </div>
</template>

<style scoped>
.sm-hero {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 30px 32px;
  border-radius: var(--sm-radius-lg);
  background: var(--sm-gradient);
  color: #fff;
  overflow: hidden;
  box-shadow: 0 18px 40px rgb(59 91 253 / 24%);
}

.sm-hero-copy {
  position: relative;
  z-index: 1;
  flex: 1;
  min-width: 0;
}

.sm-hero-eyebrow {
  font-size: 11px;
  letter-spacing: 0.18em;
  opacity: 0.78;
}

.sm-hero-title {
  margin: 6px 0 6px;
  font-size: 28px;
  font-weight: 750;
  letter-spacing: -0.02em;
}

.sm-hero-sub {
  margin: 0 0 16px;
  font-size: 13px;
  opacity: 0.88;
  max-width: 34rem;
}

.sm-hero-search {
  display: flex;
  gap: 8px;
  max-width: 34rem;
}

.sm-hero-search :deep(.el-input__wrapper) {
  border-radius: var(--sm-radius-pill);
  padding: 2px 16px;
  box-shadow: none;
}

.sm-hero-search :deep(.el-button) {
  border-radius: var(--sm-radius-pill);
  background: #fff;
  color: var(--sm-primary-dark);
  border-color: #fff;
  box-shadow: none;
}

.sm-hero-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 14px;
}

.sm-hero-tag {
  padding: 4px 12px;
  border-radius: var(--sm-radius-pill);
  border: 1px solid rgb(255 255 255 / 32%);
  background: rgb(255 255 255 / 12%);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.sm-hero-tag:hover,
.sm-hero-tag-active {
  background: #fff;
  color: var(--sm-primary-dark);
  border-color: #fff;
}

.sm-hero-art {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  font-size: 40px;
  opacity: 0.9;
  transform: rotate(-6deg);
}

.sm-hero-art span {
  display: grid;
  place-items: center;
  width: 74px;
  height: 74px;
  border-radius: 20px;
  background: rgb(255 255 255 / 16%);
  backdrop-filter: blur(3px);
}

.sm-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 16px 0;
  padding: 12px 16px;
}

.sm-toolbar-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sm-compare-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 16px;
  background: var(--sm-primary-soft);
  border-color: #d8deff;
}

.sm-block {
  margin-bottom: 12px;
}

.sm-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin: 4px 0 2px;
}

.sm-compare-wrap {
  margin-top: 16px;
}

@media (max-width: 860px) {
  .sm-hero {
    padding: 22px 20px;
  }

  .sm-hero-title {
    font-size: 22px;
  }

  .sm-hero-art {
    display: none;
  }
}
</style>
