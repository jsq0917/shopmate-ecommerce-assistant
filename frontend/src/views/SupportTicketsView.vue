<script setup lang="ts">
/**
 * 客服工单队列：按风险/原因/等待时间排序由后端完成；前端提供筛选与跳转。
 * 只能访问授权店铺的工单（后端校验），前端筛选不构成安全边界。
 */

import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElOption, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { supportApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { SupportTicketListItem } from '@/api/types'
import { formatDateTime, formatWaiting, handoffReasonLabel, riskLevelLabel, ticketStatusLabel } from '@/utils/format'

const router = useRouter()
const loading = ref(true)
const error = ref<ApiError | null>(null)
const items = ref<SupportTicketListItem[]>([])
const statusFilter = ref('')
const riskFilter = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const data = await supportApi.tickets({
      status: statusFilter.value || undefined,
      risk_level: riskFilter.value || undefined,
      limit: 50,
    })
    items.value = data.items
  } catch (caught) {
    error.value = toApiError(caught)
    items.value = []
  } finally {
    loading.value = false
  }
}

function riskType(level: string): 'danger' | 'warning' | 'info' {
  if (level === 'critical' || level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div class="sm-page">
    <div class="sm-between">
      <h2 class="sm-page-title">客服工作台 · 工单队列</h2>
      <div class="sm-row">
        <ElSelect v-model="statusFilter" placeholder="状态" clearable style="width: 9rem" @change="load">
          <ElOption value="open" label="待处理" />
          <ElOption value="assigned" label="已接管" />
          <ElOption value="resolved" label="已解决" />
          <ElOption value="closed" label="已关闭" />
        </ElSelect>
        <ElSelect v-model="riskFilter" placeholder="风险级别" clearable style="width: 9rem" @change="load">
          <ElOption value="low" label="低" />
          <ElOption value="medium" label="中" />
          <ElOption value="high" label="高" />
          <ElOption value="critical" label="紧急" />
        </ElSelect>
      </div>
    </div>

    <StateBlock
      :loading="loading && !items.length"
      :error="error"
      :empty="!loading && !error && items.length === 0"
      empty-text="当前没有需要处理的工单。"
      @retry="load"
    >
      <ElTable :data="items" style="margin-top: 12px" @row-click="(row: SupportTicketListItem) => router.push(`/support/tickets/${row.ticket_id}`)">
        <ElTableColumn label="工单号" min-width="210">
          <template #default="{ row }"><span class="sm-mono">{{ row.ticket_id }}</span></template>
        </ElTableColumn>
        <ElTableColumn label="状态" min-width="90">
          <template #default="{ row }">{{ ticketStatusLabel(row.status) }}</template>
        </ElTableColumn>
        <ElTableColumn label="风险" min-width="100">
          <template #default="{ row }">
            <ElTag size="small" :type="riskType(row.risk_level)">{{ riskLevelLabel(row.risk_level) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="主因" min-width="140">
          <template #default="{ row }">{{ handoffReasonLabel(row.primary_reason_code) }}</template>
        </ElTableColumn>
        <ElTableColumn prop="reason_codes" label="全部原因码" min-width="180">
          <template #default="{ row }">{{ row.reason_codes.map(handoffReasonLabel).join('、') }}</template>
        </ElTableColumn>
        <ElTableColumn label="优先级" min-width="80">
          <template #default="{ row }">P{{ row.priority }}</template>
        </ElTableColumn>
        <ElTableColumn prop="queue" label="队列" min-width="130" />
        <ElTableColumn label="等待" min-width="90">
          <template #default="{ row }">{{ formatWaiting(row.waiting_seconds) }}</template>
        </ElTableColumn>
        <ElTableColumn prop="user_reference_masked" label="用户（脱敏）" min-width="130" />
        <ElTableColumn label="创建时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </ElTableColumn>
      </ElTable>
    </StateBlock>
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0;
  font-size: 18px;
}
</style>
