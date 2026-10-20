<script setup lang="ts">
/**
 * 单条消息气泡。用户消息与助手消息（含工具状态、商品卡片、引用、风险标签）。
 * 未完成 / 拒答 / 转人工等状态有明确标识，不把半截回答当成功答案。
 */

import { ElAlert, ElButton, ElTag } from 'element-plus'

import DataAsOfTag from '@/components/common/DataAsOfTag.vue'
import ProductCardList from '@/components/chat/ProductCardList.vue'
import ToolStatusList from '@/components/chat/ToolStatusList.vue'
import type { TurnToolStatus } from '@/composables/useChatStream'
import type { ApiError } from '@/api/errors'
import type { MessageCitation, ProductCardData } from '@/api/types'
import { handoffReasonLabel, riskLevelLabel, routeLabel } from '@/utils/format'

export interface ChatMessageView {
  key: string
  role: 'user' | 'assistant'
  content: string
  citations: MessageCitation[]
  risk: Record<string, unknown>
  route: string | null
  finishReason: string | null
  isComplete: boolean
  createdAt: string | null
  productCards?: ProductCardData[]
  toolStatuses?: TurnToolStatus[]
  /** 本轮回答失败时的错误（仍在气泡内展示，不吞掉）。 */
  error?: ApiError | null
  stopped?: boolean
}

defineProps<{ message: ChatMessageView }>()

const emit = defineEmits<{
  (e: 'open-citations', citations: MessageCitation[]): void
  (e: 'open-product', card: ProductCardData): void
  (e: 'retry'): void
}>()

function riskTagType(level: string | undefined): 'danger' | 'warning' | 'info' {
  if (level === 'critical' || level === 'high') return 'danger'
  if (level === 'medium') return 'warning'
  return 'info'
}

function finishTag(finishReason: string | null): { label: string; type: 'info' | 'warning' | 'success' } | null {
  if (finishReason === 'refusal') return { label: '已拒答', type: 'warning' }
  if (finishReason === 'handoff') return { label: '已转人工', type: 'warning' }
  if (finishReason === 'error') return { label: '未完成', type: 'warning' }
  if (finishReason === 'cancelled') return { label: '已停止', type: 'info' }
  return null
}
</script>

<template>
  <div class="sm-message" :class="message.role === 'user' ? 'sm-message-user' : 'sm-message-assistant'">
    <div class="sm-bubble">
      <template v-if="message.role === 'user'">
        <p class="sm-bubble-text">{{ message.content }}</p>
      </template>

      <template v-else>
        <header class="sm-bubble-head">
          <span class="sm-bubble-author">ShopMate 助手</span>
          <ElTag v-if="message.route" size="small" effect="plain">{{ routeLabel(message.route) }}</ElTag>
          <ElTag
            v-if="typeof message.risk.risk_level === 'string' && message.risk.risk_level !== 'low'"
            size="small"
            :type="riskTagType(message.risk.risk_level)"
          >
            {{ riskLevelLabel(message.risk.risk_level) }}风险
            <template v-if="message.risk.primary_reason_code">
              · {{ handoffReasonLabel(String(message.risk.primary_reason_code)) }}
            </template>
          </ElTag>
          <ElTag v-if="finishTag(message.finishReason)" size="small" :type="finishTag(message.finishReason)!.type">
            {{ finishTag(message.finishReason)!.label }}
          </ElTag>
          <span v-if="!message.isComplete" class="sm-muted">（未完成，可重试或转人工）</span>
        </header>

        <p v-if="message.content" class="sm-bubble-text">{{ message.content }}</p>
        <p v-else-if="message.toolStatuses?.length" class="sm-muted">正在处理，请稍候…</p>

        <ToolStatusList v-if="message.toolStatuses?.length" :statuses="message.toolStatuses" />

        <ProductCardList
          v-if="message.productCards?.length"
          :cards="message.productCards"
          @detail="emit('open-product', $event)"
        />

        <ElAlert
          v-if="message.error"
          class="sm-bubble-error"
          type="error"
          :closable="false"
          show-icon
          :title="message.error.message"
        >
          <ElButton v-if="message.error.retryable" size="small" type="primary" @click="emit('retry')">
            重试
          </ElButton>
        </ElAlert>

        <footer v-if="message.citations.length || message.createdAt" class="sm-bubble-foot">
          <ElButton
            v-if="message.citations.length"
            size="small"
            text
            type="primary"
            @click="emit('open-citations', message.citations)"
          >
            查看引用（{{ message.citations.length }}）
          </ElButton>
          <DataAsOfTag v-if="message.createdAt" :as-of="message.createdAt" label="回答时间" />
        </footer>
      </template>
    </div>
  </div>
</template>

<style scoped>
.sm-message {
  display: flex;
  margin: 10px 0;
}

.sm-message-user {
  justify-content: flex-end;
}

.sm-message-assistant {
  justify-content: flex-start;
}

.sm-bubble {
  max-width: min(760px, 92%);
  border-radius: 12px;
  padding: 10px 14px;
  border: 1px solid var(--sm-border);
  background: var(--sm-surface);
}

.sm-message-user .sm-bubble {
  background: rgb(31 122 92 / 10%);
  border-color: rgb(31 122 92 / 25%);
}

.sm-bubble-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}

.sm-bubble-author {
  font-size: 12px;
  font-weight: 700;
  color: var(--sm-primary-dark);
}

.sm-bubble-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.sm-bubble-error {
  margin-top: 8px;
}

.sm-bubble-foot {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .sm-bubble {
    max-width: 100%;
  }
}
</style>
