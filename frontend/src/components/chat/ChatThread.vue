<script setup lang="ts">
/**
 * 消息流容器：历史消息 + 正在流式返回的本轮回答；智能滚动到底部。
 *
 * 滚动规则（stick-to-bottom）：
 * - 距底部不足 NEAR_BOTTOM_PX 时视为“贴底”，新内容到达自动跟随滚动；
 * - 用户向上翻阅历史后不再自动滚动，直到手动回到底部附近；
 * - 会话切换（messages 整体替换）与新发送的用户消息强制滚底。
 *
 * 滚动容器是本组件根元素自身：父级（ChatView 的 StateBlock stretch 模式）
 * 提供了确定的高度约束，overflow-y 才能生效。
 */

import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import MessageBubble, { type ChatMessageView } from '@/components/chat/MessageBubble.vue'
import type { TurnState } from '@/composables/useChatStream'
import type { MessageCitation, ProductCardData } from '@/api/types'

const NEAR_BOTTOM_PX = 80

const props = defineProps<{
  messages: ChatMessageView[]
  turn: TurnState
  /** 当前会话 id：仅在真正切换会话时强制滚底；同会话的历史刷新不打扰用户。 */
  conversationId: string | null
}>()

const emit = defineEmits<{
  (e: 'open-citations', citations: MessageCitation[]): void
  (e: 'open-product', card: ProductCardData): void
  (e: 'retry'): void
}>()

const scroller = ref<HTMLElement | null>(null)
const streamingMessage = ref<ChatMessageView | null>(null)

/** 流已建立但还没有任何可见产出时的“正在思考”占位。 */
const thinking = ref(false)

/** 用户是否停留在消息底部附近（自动跟随仅在此时生效）。 */
const stickToBottom = ref(true)

function isNearBottom(element: HTMLElement): boolean {
  return element.scrollHeight - element.scrollTop - element.clientHeight < NEAR_BOTTOM_PX
}

async function scrollToBottom(force = false): Promise<void> {
  const element = scroller.value
  if (!element) return
  if (!force && !stickToBottom.value) return
  await nextTick()
  element.scrollTop = element.scrollHeight
}

function onScroll(): void {
  const element = scroller.value
  if (element) stickToBottom.value = isNearBottom(element)
}

onMounted(() => {
  void scrollToBottom(true)
})

onBeforeUnmount(() => {
  scroller.value?.removeEventListener('scroll', onScroll)
})

watch(
  scroller,
  (element) => {
    element?.addEventListener('scroll', onScroll, { passive: true })
  },
  { immediate: true },
)

watch(
  () => props.conversationId,
  () => {
    // 会话切换：回到新会话的最新消息。loadMessages 造成的同会话数组替换不走这里，
    // 否则每轮回答结束都会把正在翻历史的用户拽回底部。
    void scrollToBottom(true)
  },
)

watch(
  () => [props.messages.length, props.turn.text, props.turn.active, props.turn.toolStatuses.length] as const,
  ([length], previous) => {
    // 用户刚发出一条消息：发送动作意味着关注最新内容，无条件跟随。
    const newUserMessage =
      previous !== undefined &&
      length > previous[0] &&
      props.messages[length - 1]?.role === 'user'
    void scrollToBottom(newUserMessage)
  },
)

watch(
  () => props.turn,
  (turn) => {
    thinking.value =
      turn.active &&
      turn.text === '' &&
      turn.toolStatuses.length === 0 &&
      turn.productCards.length === 0 &&
      turn.citations.length === 0 &&
      !turn.error
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
    if (thinking.value) {
      // 思考期间不渲染空气泡，改由打字指示器占位。
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
    <p v-if="!messages.length && !streamingMessage && !thinking" class="sm-thread-empty sm-muted">
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

    <div v-if="thinking" class="sm-thinking" data-testid="thinking-indicator">
      <span class="sm-thinking-dot" aria-hidden="true" />
      <span class="sm-thinking-dot" aria-hidden="true" />
      <span class="sm-thinking-dot" aria-hidden="true" />
      <span class="sm-thinking-label">ShopMate 正在思考…</span>
    </div>

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

.sm-thinking {
  display: flex;
  align-items: center;
  gap: 5px;
  margin: 12px 2px;
  padding: 10px 14px;
  width: fit-content;
  border-radius: var(--sm-radius);
  background: var(--sm-bg);
  border: 1px solid var(--sm-border);
}

.sm-thinking-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sm-primary);
  animation: sm-thinking-bounce 1.2s infinite ease-in-out;
}

.sm-thinking-dot:nth-child(2) {
  animation-delay: 0.15s;
}

.sm-thinking-dot:nth-child(3) {
  animation-delay: 0.3s;
}

.sm-thinking-label {
  margin-left: 6px;
  font-size: 12px;
  color: var(--sm-text-tertiary);
}

@keyframes sm-thinking-bounce {
  0%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-3px);
  }
}
</style>
