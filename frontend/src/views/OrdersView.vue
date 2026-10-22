<script setup lang="ts">
/**
 * 订单列表：状态筛选 + 分页。越权/不存在的订单由后端统一返回 404，
 * 前端不推断资源是否存在（业务铁律 4）。
 */

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElTag } from 'element-plus'

import ProductThumb from '@/components/common/ProductThumb.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { ordersApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { OrderListData, OrderListItem } from '@/api/types'
import { formatDateTime, formatMoney, orderStatusLabel } from '@/utils/format'

const router = useRouter()
const loading = ref(true)
const error = ref<ApiError | null>(null)
const data = ref<OrderListData | null>(null)
const statusFilter = ref('')
const offset = ref(0)
const limit = 20

const statusOptions = [
  { value: '', label: '全部' },
  { value: 'created', label: '待付款' },
  { value: 'paid', label: '待发货' },
  { value: 'processing', label: '备货中' },
  { value: 'shipped', label: '已发货' },
  { value: 'delivered', label: '已签收' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
]

const items = computed(() => data.value?.items ?? [])

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    data.value = await ordersApi.list({
      status: statusFilter.value || undefined,
      limit,
      offset: offset.value,
    })
  } catch (caught) {
    error.value = toApiError(caught)
    data.value = null
  } finally {
    loading.value = false
  }
}

function switchStatus(value: string): void {
  statusFilter.value = value
  offset.value = 0
  void load()
}

function statusTagType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'completed' || status === 'delivered') return 'success'
  if (status === 'cancelled') return 'danger'
  if (status === 'shipped' || status === 'processing') return 'warning'
  return 'info'
}

function open(row: OrderListItem): void {
  void router.push(`/orders/${row.id}`)
}

onMounted(load)
</script>

<template>
  <div class="sm-page">
    <div class="sm-page-header">
      <div>
        <h2 class="sm-page-title">我的订单</h2>
        <p class="sm-page-subtitle">价格、状态与物流均来自订单系统；未支付的订单可以取消。</p>
      </div>
      <ElButton @click="router.push('/products')">继续购物</ElButton>
    </div>

    <div class="sm-status-tabs">
      <button
        v-for="option in statusOptions"
        :key="option.value"
        type="button"
        class="sm-status-tab"
        :class="{ 'sm-status-tab-active': statusFilter === option.value }"
        @click="switchStatus(option.value)"
      >
        {{ option.label }}
      </button>
    </div>

    <StateBlock
      :loading="loading && !data"
      :error="error"
      :empty="!loading && !error && items.length === 0"
      empty-text="当前账号下没有订单。去商品中心挑一件吧。"
      @retry="load"
    >
      <div class="sm-order-list">
        <article
          v-for="row in items"
          :key="row.id"
          class="sm-order-card sm-card-hover"
          @click="open(row)"
        >
          <header class="sm-order-head">
            <span class="sm-order-no sm-mono">{{ row.order_no }}</span>
            <ElTag size="small" :type="statusTagType(row.status)" effect="light">
              {{ orderStatusLabel(row.status) }}
            </ElTag>
            <span v-if="row.is_synthetic" class="sm-synthetic-tag">合成</span>
            <span class="sm-order-time">{{ formatDateTime(row.placed_at) }}</span>
          </header>

          <div class="sm-order-body">
            <ProductThumb size="sm" :title="row.first_item_title ?? row.order_no" />
            <div class="sm-order-main">
              <p class="sm-order-title">{{ row.first_item_title ?? '订单商品' }}</p>
              <p class="sm-muted">共 {{ row.item_count }} 件商品</p>
            </div>
            <div class="sm-order-amount">
              <span class="sm-muted">实付</span>
              <strong class="sm-price">{{ formatMoney(row.total_cents, row.currency) }}</strong>
            </div>
          </div>

          <footer class="sm-order-foot">
            <span class="sm-muted">状态更新 {{ formatDateTime(row.status_updated_at) }}</span>
            <ElButton size="small" @click.stop="open(row)">
              {{ row.status === 'created' ? '去支付' : '查看详情' }}
            </ElButton>
          </footer>
        </article>
      </div>

      <div v-if="data?.next_offset != null || offset > 0" class="sm-between sm-pager">
        <ElButton size="small" :disabled="offset === 0" @click="offset = Math.max(0, offset - limit); load()">
          上一页
        </ElButton>
        <ElButton size="small" :disabled="data?.next_offset == null" @click="offset = data?.next_offset ?? offset; load()">
          下一页
        </ElButton>
      </div>
    </StateBlock>
  </div>
</template>

<style scoped>
.sm-status-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
  overflow-x: auto;
  scrollbar-width: none;
}

.sm-status-tabs::-webkit-scrollbar {
  display: none;
}

.sm-status-tab {
  padding: 6px 14px;
  border-radius: 999px;
  border: 1px solid var(--sm-border);
  background: var(--sm-surface);
  color: var(--sm-text-secondary);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease;
}

.sm-status-tab:hover {
  border-color: #c5ceff;
  color: var(--sm-primary-dark);
}

.sm-status-tab-active {
  background: var(--sm-primary);
  border-color: var(--sm-primary);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 6px 16px rgb(59 91 253 / 22%);
}

.sm-order-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sm-order-card {
  padding: 16px 18px;
  cursor: pointer;
}

.sm-order-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.sm-order-no {
  font-weight: 650;
  color: var(--sm-text);
}

.sm-order-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--sm-text-tertiary);
}

.sm-synthetic-tag {
  padding: 0 7px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 10px;
}

.sm-order-body {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 12px 0;
}

.sm-order-main {
  flex: 1;
  min-width: 0;
}

.sm-order-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sm-order-amount {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
}

.sm-order-amount strong {
  font-size: 18px;
}

.sm-order-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px dashed var(--sm-border);
}

.sm-pager {
  margin-top: 16px;
}
</style>
