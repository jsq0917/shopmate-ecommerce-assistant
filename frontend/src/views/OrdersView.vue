<script setup lang="ts">
/**
 * 订单列表：状态筛选 + 分页。越权/不存在的订单由后端统一返回 404，
 * 前端不推断资源是否存在（业务铁律 4）。
 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElOption, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'

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
  { value: '', label: '全部状态' },
  { value: 'created', label: '已下单' },
  { value: 'paid', label: '已付款' },
  { value: 'processing', label: '处理中' },
  { value: 'shipped', label: '已发货' },
  { value: 'delivered', label: '已送达' },
  { value: 'completed', label: '已完成' },
  { value: 'cancelled', label: '已取消' },
]

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

function statusTagType(status: string): 'success' | 'warning' | 'info' | 'danger' {
  if (status === 'completed' || status === 'delivered') return 'success'
  if (status === 'cancelled') return 'danger'
  if (status === 'shipped' || status === 'processing') return 'warning'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div class="sm-page">
    <div class="sm-between">
      <h2 class="sm-page-title">我的订单</h2>
      <ElSelect v-model="statusFilter" style="width: 10rem" @change="offset = 0; load()">
        <ElOption v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
      </ElSelect>
    </div>

    <StateBlock
      :loading="loading && !data"
      :error="error"
      :empty="!loading && !error && (data?.items.length ?? 0) === 0"
      empty-text="当前账号下没有订单。"
      @retry="load"
    >
      <ElTable :data="data?.items ?? []" style="margin-top: 12px" @row-click="(row: OrderListItem) => router.push(`/orders/${row.id}`)">
        <ElTableColumn prop="order_no" label="订单号" min-width="130" />
        <ElTableColumn label="状态" min-width="100">
          <template #default="{ row }">
            <ElTag size="small" :type="statusTagType(row.status)">{{ orderStatusLabel(row.status) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="金额" min-width="110">
          <template #default="{ row }">{{ formatMoney(row.total_cents, row.currency) }}</template>
        </ElTableColumn>
        <ElTableColumn label="下单时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.placed_at) }}</template>
        </ElTableColumn>
        <ElTableColumn label="状态更新时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.status_updated_at) }}</template>
        </ElTableColumn>
        <ElTableColumn label="数据" min-width="80">
          <template #default="{ row }">
            <span v-if="row.is_synthetic" class="sm-synthetic-tag">合成</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="操作" width="90">
          <template #default="{ row }">
            <ElButton size="small" text type="primary" @click.stop="router.push(`/orders/${row.id}`)">详情</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>

      <div v-if="data?.next_offset != null" class="sm-between sm-pager">
        <ElButton size="small" :disabled="offset === 0" @click="offset = Math.max(0, offset - limit); load()">上一页</ElButton>
        <ElButton size="small" @click="offset = data.next_offset; load()">下一页</ElButton>
      </div>
    </StateBlock>
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0;
  font-size: 18px;
}

.sm-pager {
  margin-top: 12px;
}

.sm-synthetic-tag {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}
</style>
