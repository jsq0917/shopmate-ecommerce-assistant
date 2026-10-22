<script setup lang="ts">
/**
 * 客服视角的会话解释面板：消息、引用、工具调用摘要、风险标签。
 * 不展示系统 prompt、密钥、内部堆栈或完整 PII（docs/06-api.md 第 12 节）。
 */

import { ref } from 'vue'
import { ElButton, ElTable, ElTableColumn, ElTag } from 'element-plus'

import type { SupportConversation } from '@/api/types'
import {
  formatDateTime,
  handoffReasonLabel,
  riskLevelLabel,
  ticketStatusLabel,
} from '@/utils/format'

defineProps<{ conversation: SupportConversation }>()

const expandedCitation = ref<string | null>(null)

/** 客服回复以 assistant + route=support_agent 落库，这里据此改称呼。 */
function roleLabel(message: { role: string; risk?: Record<string, unknown> }): string {
  if (message.risk && message.risk.author === 'support_agent') return '人工客服'
  return message.role === 'assistant' ? 'AI 助手' : '用户'
}

function isAgent(message: { risk?: Record<string, unknown> }): boolean {
  return Boolean(message.risk && message.risk.author === 'support_agent')
}

function riskType(level: string | undefined): 'danger' | 'warning' | 'info' {
  if (level === 'critical' || level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}
</script>

<template>
  <div class="sm-support-conversation">
    <div class="sm-between">
      <h3 class="sm-section-title">会话：{{ conversation.title }}</h3>
      <span class="sm-muted">用户标识（脱敏）：{{ conversation.owner_reference_masked }}</span>
    </div>

    <ol class="sm-support-messages">
      <li v-for="message in conversation.messages" :key="message.message_id" class="sm-support-message">
        <header class="sm-support-message-head">
          <span class="sm-support-role" :class="{ 'sm-support-role-agent': isAgent(message) }">
            {{ roleLabel(message) }}
          </span>
          <span v-if="message.role === 'assistant' && !message.is_complete" class="sm-muted">（未完成）</span>
          <ElTag
            v-if="message.risk && message.risk.risk_level && message.risk.risk_level !== 'low'"
            size="small"
            :type="riskType(message.risk.risk_level)"
          >
            {{ riskLevelLabel(message.risk.risk_level) }}风险
            <template v-if="message.risk.primary_reason_code">
              · {{ handoffReasonLabel(String(message.risk.primary_reason_code)) }}
            </template>
          </ElTag>
          <span class="sm-muted">{{ formatDateTime(message.created_at) }}</span>
        </header>
        <p class="sm-support-text">{{ message.content }}</p>
        <div v-if="message.citations.length" class="sm-support-citations">
          <ElButton
            size="small"
            text
            type="primary"
            @click="expandedCitation = expandedCitation === message.message_id ? null : message.message_id"
          >
            引用（{{ message.citations.length }}）
            {{ expandedCitation === message.message_id ? '收起' : '展开' }}
          </ElButton>
          <ul v-if="expandedCitation === message.message_id" class="sm-citation-list">
            <li v-for="citation in message.citations" :key="citation.citation_id">
              <span class="sm-citation-label">{{ citation.label ?? '' }}</span>
              《{{ citation.title }}》
              <span v-if="citation.heading"> · {{ citation.heading }}</span>
              <span v-if="citation.page_no !== null"> · 第 {{ citation.page_no }} 页</span>
              · 版本 {{ citation.version }}
              <span v-if="citation.excerpt" class="sm-citation-excerpt"> — {{ citation.excerpt }}</span>
            </li>
          </ul>
        </div>
      </li>
    </ol>

    <h4 class="sm-section-title">工具调用摘要</h4>
    <ElTable :data="conversation.tool_calls" size="small" border>
      <ElTableColumn prop="tool_name" label="工具" min-width="150" />
      <ElTableColumn prop="status" label="状态" min-width="90" />
      <ElTableColumn label="耗时" min-width="90">
        <template #default="{ row }">{{ row.latency_ms !== null ? `${row.latency_ms} ms` : '--' }}</template>
      </ElTableColumn>
      <ElTableColumn label="结果摘要" min-width="220">
        <template #default="{ row }">
          <span class="sm-mono">{{ JSON.stringify(row.result_summary) }}</span>
        </template>
      </ElTableColumn>
    </ElTable>

    <div v-if="conversation.handoff" class="sm-support-handoff">
      <h4 class="sm-section-title">关联工单</h4>
      <p class="sm-muted">
        工单 <span class="sm-mono">{{ conversation.handoff.ticket_id }}</span> ·
        {{ ticketStatusLabel(conversation.handoff.status) }} ·
        主因 {{ handoffReasonLabel(conversation.handoff.primary_reason_code) }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.sm-section-title {
  margin: 12px 0 8px;
  font-size: 15px;
}

.sm-support-messages {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sm-support-message {
  border: 1px solid var(--sm-border);
  border-radius: 8px;
  padding: 8px 12px;
}

.sm-support-message-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.sm-support-role {
  font-weight: 700;
}

.sm-support-role-agent {
  color: var(--sm-accent);
}

.sm-support-text {
  margin: 6px 0 0;
  white-space: pre-wrap;
}

.sm-citation-list {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--sm-text-secondary);
}

.sm-citation-label {
  display: inline-block;
  min-width: 20px;
  font-weight: 700;
  color: var(--sm-primary-dark);
}

.sm-support-handoff {
  margin-top: 12px;
}
</style>
