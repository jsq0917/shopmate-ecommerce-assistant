<script setup lang="ts">
/**
 * 我的工单（消费者侧）：只展示当前账号的人工工单与脱敏摘要。
 * 客服的人工回复不会单独存一份，而是写回原会话，所以这里引导用户回聊天页查看。
 */

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElButton, ElTag } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { handoffApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { HandoffListItem } from '@/api/types'
import { formatDateTime, handoffReasonLabel, riskLevelLabel, ticketStatusLabel } from '@/utils/format'

const router = useRouter()
const loading = ref(true)
const error = ref<ApiError | null>(null)
const items = ref<HandoffListItem[]>([])

const activeCount = computed(
  () => items.value.filter((item) => item.status === 'open' || item.status === 'assigned').length,
)

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

function statusType(status: string): 'success' | 'warning' | 'info' {
  if (status === 'resolved' || status === 'closed') return 'success'
  if (status === 'assigned') return 'warning'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div class="sm-page">
    <div class="sm-page-header">
      <div>
        <h2 class="sm-page-title">我的工单</h2>
        <p class="sm-page-subtitle">
          转人工后由客服跟进；回复会出现在原聊天会话里，共 {{ activeCount }} 个进行中的工单。
        </p>
      </div>
      <ElButton type="primary" plain @click="router.push('/')">回到聊天</ElButton>
    </div>

    <StateBlock
      :loading="loading && !items.length"
      :error="error"
      :empty="!loading && !error && items.length === 0"
      empty-text="暂无工单。在聊天页点击“转人工”即可创建。"
      @retry="load"
    >
      <div class="sm-ticket-list">
        <article v-for="row in items" :key="row.ticket_id" class="sm-ticket-card">
          <div class="sm-ticket-top">
            <ElTag size="small" :type="statusType(row.status)" effect="light">
              {{ ticketStatusLabel(row.status) }}
            </ElTag>
            <ElTag size="small" :type="riskType(row.risk_level)" effect="plain">
              {{ riskLevelLabel(row.risk_level) }}风险
            </ElTag>
            <span class="sm-ticket-reason">{{ handoffReasonLabel(row.primary_reason_code) }}</span>
            <span class="sm-ticket-time">{{ formatDateTime(row.created_at) }}</span>
          </div>

          <p class="sm-ticket-summary">{{ row.summary_redacted || '（无摘要）' }}</p>

          <div class="sm-ticket-foot">
            <span class="sm-muted">
              工单 <span class="sm-mono">{{ row.ticket_id }}</span>
              · 预计响应 {{ row.expected_response || '—' }}
            </span>
            <span class="sm-muted">
              客服回复请在 <router-link to="/">聊天页</router-link> 查看
            </span>
          </div>
        </article>
      </div>
    </StateBlock>
  </div>
</template>

<style scoped>
.sm-ticket-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sm-ticket-card {
  padding: 16px 18px;
  background: var(--sm-surface);
  border: 1px solid var(--sm-border);
  border-radius: var(--sm-radius);
  box-shadow: var(--sm-shadow-xs);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sm-ticket-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sm-ticket-reason {
  font-weight: 650;
  font-size: 14px;
}

.sm-ticket-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--sm-text-tertiary);
}

.sm-ticket-summary {
  margin: 0;
  color: var(--sm-text-secondary);
  font-size: 13px;
}

.sm-ticket-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px dashed var(--sm-border);
}
</style>
