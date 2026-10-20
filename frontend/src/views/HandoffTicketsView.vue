<script setup lang="ts">
/**
 * 我的工单（消费者侧）：只展示当前账号的人工工单与脱敏摘要。
 */

import { onMounted, ref } from 'vue'
import { ElTable, ElTableColumn, ElTag } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { handoffApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { HandoffListItem } from '@/api/types'
import { formatDateTime, handoffReasonLabel, riskLevelLabel, ticketStatusLabel } from '@/utils/format'

const loading = ref(true)
const error = ref<ApiError | null>(null)
const items = ref<HandoffListItem[]>([])

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const data = await handoffApi.list({ limit: 50 })
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
    <h2 class="sm-page-title">我的工单</h2>
    <p class="sm-muted">转人工后由客服跟进；工单进度与预计响应时间如下。</p>

    <StateBlock
      :loading="loading && !items.length"
      :error="error"
      :empty="!loading && !error && items.length === 0"
      empty-text="暂无工单。在聊天页点击“转人工”可创建。"
      @retry="load"
    >
      <ElTable :data="items" style="margin-top: 12px">
        <ElTableColumn label="工单号" min-width="220">
          <template #default="{ row }"><span class="sm-mono">{{ row.ticket_id }}</span></template>
        </ElTableColumn>
        <ElTableColumn label="状态" min-width="90">
          <template #default="{ row }">{{ ticketStatusLabel(row.status) }}</template>
        </ElTableColumn>
        <ElTableColumn label="风险" min-width="110">
          <template #default="{ row }">
            <ElTag size="small" :type="riskType(row.risk_level)">{{ riskLevelLabel(row.risk_level) }}</ElTag>
          </template>
        </ElTableColumn>
        <ElTableColumn label="主要原因" min-width="140">
          <template #default="{ row }">{{ handoffReasonLabel(row.primary_reason_code) }}</template>
        </ElTableColumn>
        <ElTableColumn prop="summary_redacted" label="摘要" min-width="220" show-overflow-tooltip />
        <ElTableColumn prop="expected_response" label="预计响应" min-width="140" show-overflow-tooltip />
        <ElTableColumn label="创建时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </ElTableColumn>
      </ElTable>
    </StateBlock>
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0 0 4px;
  font-size: 18px;
}
</style>
