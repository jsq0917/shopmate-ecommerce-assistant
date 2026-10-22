<script setup lang="ts">
/**
 * 消息流容器：历史消息 + 正在流式返回的本轮回答；自动滚动到底部。
 */

import { nextTick, ref, watch } from 'vue'

import MessageBubble, { type ChatMessageView } from '@/components/chat/MessageBubble.vue'
import type { TurnState } from '@/composables/useChatStream'
import type { MessageCitation, ProductCardData } from '@/api/types'

const props = defineProps<{
  messages: ChatMessageView[]
  turn: TurnState
}>()

const emit = defineEmits<{
  (e: 'open-citations', citations: MessageCitation[]): void
  (e: 'open-product', card: ProductCardData): void
  (e: 'retry'): void
}>()

const scroller = ref<HTMLElement | null>(null)

const streamingMessage = ref<ChatMessageView | null>(null)

watch(
  () => [props.messages.length, props.turn.text, props.turn.active, props.turn.toolStatuses.length],
  async () => {
    await nextTick()
    const element = scroller.value
    if (element) element.scrollTop = element.scrollHeight
  },
  { deep: true },
)

watch(
  () => props.turn,
  (turn) => {
    // 断线/失败时 turn 可能没有任何正文，但错误提示必须仍然可见（可重试）。
    if (
      !turn.active &&
      turn.text === '' &&
      turn.toolStatuses.length === 0 &&
      turn.productCards.length === 0 &&
      !turn.error &&
      !turn.stopped
    ) {
      streamingMessage.value = null
      return
    }
    streamingMessage.value = {
      key: 'streaming',
      role: 'assistant',
      content: turn.text,
      citations: turn.citations,
      risk: {},
      route: turn.route,
      finishReason: turn.finishReason,
      isComplete: !turn.active,
      createdAt: null,
      productCards: turn.productCards,
      toolStatuses: turn.toolStatuses,
      error: turn.error,
      stopped: turn.stopped,
    }
  },
  { deep: true, immediate: true },
)
</script>

<template>
  <div ref="scroller" class="sm-thread" aria-live="polite">
    <p v-if="!messages.length && !streamingMessage" class="sm-thread-empty sm-muted">
      还没有消息，输入问题就开始对话。
    </p>

    <MessageBubble
      v-for="message in messages"
      :key="message.key"
      :message="message"
      @open-citations="emit('open-citations', $event)"
      @open-product="emit('open-product', $event)"
      @retry="emit('retry')"
    />

    <MessageBubble
      v-if="streamingMessage"
      :message="streamingMessage"
      @open-citations="emit('open-citations', $event)"
      @open-product="emit('open-product', $event)"
      @retry="emit('retry')"
    />
  </div>
</template>

<style scoped>
.sm-thread {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 24px 8px;
  background:
    radial-gradient(900px 320px at 15% -10%, rgb(59 91 253 / 6%), transparent 70%),
    radial-gradient(700px 280px at 90% 0%, rgb(154 107 255 / 5%), transparent 70%),
    var(--sm-surface);
}

.sm-thread-empty {
  margin-top: 24px;
  text-align: center;
}
</style>
