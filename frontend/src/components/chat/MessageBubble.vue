<script setup lang="ts">
/**
 * 单条消息气泡。用户消息与助手消息（含工具状态、商品卡片、引用、风险标签）。
 * 未完成 / 拒答 / 转人工等状态有明确标识，不把半截回答当成功答案。
 *
 * 富文本只做「先转义、再插 strong/br」的最小渲染：后端内容与模型输出都按不可信文本处理。
 */

import { computed } from 'vue'
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

const props = defineProps<{ message: ChatMessageView; showAvatar?: boolean }>()

const emit = defineEmits<{
  (e: 'open-citations', citations: MessageCitation[]): void
  (e: 'open-product', card: ProductCardData): void
  (e: 'retry'): void
}>()

const isAgent = computed(() => props.message.route === 'support_agent')

const authorLabel = computed(() => (isAgent.value ? '人工客服' : 'ShopMate 助手'))

const timeLabel = computed(() => {
  if (!props.message.createdAt) return ''
  const date = new Date(props.message.createdAt)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
})

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

const richContent = computed(() => {
  const text = props.message.content ?? ''
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
})

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

async function copyContent(): Promise<void> {
  try {
    await navigator.clipboard.writeText(props.message.content)
  } catch {
    // 剪贴板不可用时保持静默：复制只是一个便利功能。
  }
}
</script>

<template>
  <div
    class="sm-message"
    :class="message.role === 'user' ? 'sm-message-user' : 'sm-message-assistant'"
  >
    <span v-if="message.role === 'assistant'" class="sm-avatar sm-avatar-ai" aria-hidden="true">SM</span>
    <div class="sm-bubble-wrap">
      <div class="sm-bubble" :class="{ 'sm-bubble-agent': isAgent }">
        <template v-if="message.role === 'user'">
          <p class="sm-bubble-text">{{ message.content }}</p>
        </template>

        <template v-else>
          <header class="sm-bubble-head">
            <span class="sm-bubble-author">{{ authorLabel }}</span>
            <ElTag v-if="message.route && !isAgent" size="small" effect="plain">
              {{ routeLabel(message.route) }}
            </ElTag>
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
            <span v-if="timeLabel" class="sm-bubble-time">{{ timeLabel }}</span>
          </header>

          <p v-if="message.content" class="sm-bubble-text sm-rich" v-html="richContent" />
          <p v-else-if="message.toolStatuses?.length" class="sm-muted sm-bubble-wait">
            正在处理
            <span class="sm-typing"><i /><i /><i /></span>
          </p>

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

          <footer class="sm-bubble-foot">
            <span class="sm-row">
              <ElButton
                v-if="message.citations.length"
                size="small"
                text
                type="primary"
                @click="emit('open-citations', message.citations)"
              >
                查看引用（{{ message.citations.length }}）
              </ElButton>
              <ElButton v-if="message.content" size="small" text @click="copyContent">复制</ElButton>
            </span>
            <DataAsOfTag v-if="message.createdAt" :as-of="message.createdAt" label="回答时间" />
          </footer>
        </template>
      </div>
      <span v-if="message.role === 'user' && timeLabel" class="sm-user-time">{{ timeLabel }}</span>
    </div>
  </div>
</template>

<style scoped>
.sm-message {
  display: flex;
  gap: 10px;
  margin: 14px 0;
  align-items: flex-start;
}

.sm-message-user {
  justify-content: flex-end;
}

.sm-avatar {
  flex: none;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.02em;
}

.sm-avatar-ai {
  background: var(--sm-gradient);
  color: #fff;
  box-shadow: 0 4px 12px rgb(59 91 253 / 26%);
}

.sm-bubble-wrap {
  max-width: min(760px, 82%);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.sm-message-user .sm-bubble-wrap {
  align-items: flex-end;
}

.sm-bubble {
  border-radius: 16px;
  padding: 12px 16px;
  border: 1px solid var(--sm-border);
  background: var(--sm-surface);
  box-shadow: var(--sm-shadow-xs);
}

.sm-message-user .sm-bubble {
  background: linear-gradient(135deg, #3b5bfd 0%, #6d5efc 100%);
  border-color: transparent;
  color: #fff;
  border-bottom-right-radius: 6px;
  box-shadow: 0 8px 20px rgb(59 91 253 / 22%);
}

.sm-message-assistant .sm-bubble {
  border-bottom-left-radius: 6px;
}

.sm-bubble-agent {
  border-color: #ffe0c7;
  background: linear-gradient(180deg, #fffaf5 0%, #ffffff 60%);
}

.sm-bubble-head {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 6px;
}

.sm-bubble-author {
  font-size: 12px;
  font-weight: 700;
  color: var(--sm-primary-dark);
}

.sm-bubble-agent .sm-bubble-author {
  color: var(--sm-accent);
}

.sm-bubble-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--sm-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.sm-bubble-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 14px;
  line-height: 1.72;
}

.sm-rich :deep(strong) {
  font-weight: 700;
}

.sm-message-user .sm-bubble-text {
  white-space: pre-wrap;
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

.sm-user-time {
  font-size: 11px;
  color: var(--sm-text-tertiary);
  padding-right: 4px;
}

/* 等待首个 token 的三点动画 */
.sm-bubble-wait {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.sm-typing {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.sm-typing i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--sm-primary);
  opacity: 0.35;
  animation: sm-blink 1.1s infinite ease-in-out;
}

.sm-typing i:nth-child(2) {
  animation-delay: 0.18s;
}

.sm-typing i:nth-child(3) {
  animation-delay: 0.36s;
}

@keyframes sm-blink {
  0%,
  80%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

@media (max-width: 768px) {
  .sm-bubble-wrap {
    max-width: calc(100% - 42px);
  }

  .sm-avatar {
    width: 28px;
    height: 28px;
  }
}
</style>
