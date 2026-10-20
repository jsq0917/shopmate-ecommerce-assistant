<script setup lang="ts">
/**
 * 消费者聊天页：会话管理 + SSE 流式回答 + 工具状态 + 商品卡片 + 引用侧栏。
 *
 * 约束：
 * - 会话/消息只经 REST 与 SSE 获取，不直连任何存储；
 * - 断线/失败有明确提示，半截回答标记“未完成”；
 * - 不展示 token、trace_id 或任何内部字段。
 */

import { computed, onMounted, ref } from 'vue'
import { ElButton, ElDrawer } from 'element-plus'

import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatThread from '@/components/chat/ChatThread.vue'
import CitationPanel from '@/components/chat/CitationPanel.vue'
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import HandoffDialog from '@/components/chat/HandoffDialog.vue'
import ProductDetailDialog from '@/components/catalog/ProductDetailDialog.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { conversationsApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { ChatMessageView } from '@/components/chat/MessageBubble.vue'
import type { ConversationItem, MessageCitation, MessageItem, ProductCardData } from '@/api/types'
import { useChatStream } from '@/composables/useChatStream'
import { routeLabel } from '@/utils/format'

defineOptions({ name: 'ChatView' })

const { turn, send, stop, resetTurn } = useChatStream()

const conversations = ref<ConversationItem[]>([])
const activeId = ref<string | null>(null)
const listLoading = ref(true)
const listError = ref<ApiError | null>(null)

const messages = ref<ChatMessageView[]>([])
const messagesLoading = ref(false)
const messagesError = ref<ApiError | null>(null)

const sidebarOpen = ref(false)
const citationDrawerVisible = ref(false)
const drawerCitations = ref<MessageCitation[]>([])
const detailVisible = ref(false)
const detailProductId = ref<string | null>(null)
const handoffVisible = ref(false)

const lastUserText = ref('')
const busy = computed(() => turn.value.active)

function toView(item: MessageItem): ChatMessageView {
  return {
    key: item.id,
    role: item.role,
    content: item.content,
    citations: item.citations ?? [],
    risk: (item.risk ?? {}) as Record<string, unknown>,
    route: item.route,
    finishReason: item.finish_reason,
    isComplete: item.is_complete,
    createdAt: item.created_at,
  }
}

async function loadConversations(): Promise<void> {
  listLoading.value = true
  listError.value = null
  try {
    const data = await conversationsApi.list({ limit: 50 })
    conversations.value = data.items
    if (!activeId.value && data.items.length) {
      await selectConversation(data.items[0].id)
    }
    if (!data.items.length) {
      await createConversation()
    }
  } catch (caught) {
    listError.value = toApiError(caught)
  } finally {
    listLoading.value = false
  }
}

async function loadMessages(conversationId: string): Promise<void> {
  messagesLoading.value = true
  messagesError.value = null
  try {
    const data = await conversationsApi.messages(conversationId, { limit: 100 })
    messages.value = data.items.map(toView)
  } catch (caught) {
    messagesError.value = toApiError(caught)
    messages.value = []
  } finally {
    messagesLoading.value = false
  }
}

async function selectConversation(id: string): Promise<void> {
  if (turn.value.active) return
  activeId.value = id
  sidebarOpen.value = false
  resetTurn()
  await loadMessages(id)
}

async function createConversation(): Promise<void> {
  if (turn.value.active) return
  try {
    const created = await conversationsApi.create()
    conversations.value = [created, ...conversations.value]
    await selectConversation(created.id)
  } catch (caught) {
    listError.value = toApiError(caught)
  }
}

async function renameConversation(id: string, title: string): Promise<void> {
  try {
    const updated = await conversationsApi.rename(id, title)
    conversations.value = conversations.value.map((item) => (item.id === id ? updated : item))
  } catch (caught) {
    listError.value = toApiError(caught)
  }
}

async function removeConversation(id: string): Promise<void> {
  try {
    await conversationsApi.remove(id)
    conversations.value = conversations.value.filter((item) => item.id !== id)
    if (activeId.value === id) {
      const next = conversations.value[0]
      if (next) {
        await selectConversation(next.id)
      } else {
        activeId.value = null
        messages.value = []
        await createConversation()
      }
    }
  } catch (caught) {
    listError.value = toApiError(caught)
  }
}

async function onSend(text: string): Promise<void> {
  if (!activeId.value || turn.value.active) return
  lastUserText.value = text
  const conversationId = activeId.value

  const result = await send(conversationId, text)
  // 服务端在建立流之前拒绝了重复/进行中的请求，或用户主动停止：
  // 一律以服务端持久化历史为准，避免出现“前端有、库里无”的消息。
  if (result.duplicate || result.outcome === 'stopped') {
    resetTurn()
    await loadMessages(conversationId)
    return
  }
  await loadMessages(conversationId)
  // 网络断线：必须把错误留在界面上（含“重试”入口），否则用户只看到消息消失、
  // 无法判断是发送失败还是正在处理。重试会通过 send() 清空本轮的 turn。
  if (result.outcome === 'network') return
  resetTurn()
}

function onRetry(): void {
  if (lastUserText.value) void onSend(lastUserText.value)
}

function onOpenCitations(citations: MessageCitation[]): void {
  drawerCitations.value = citations
  citationDrawerVisible.value = true
}

function onOpenProduct(card: ProductCardData): void {
  detailProductId.value = card.product_id
  detailVisible.value = true
}

onMounted(() => {
  void loadConversations()
})
</script>

<template>
  <div class="sm-chat">
    <div class="sm-chat-sidebar" :class="{ 'sm-chat-sidebar-open': sidebarOpen }">
      <StateBlock :loading="listLoading" :error="listError" :empty="!listLoading && !listError && !conversations.length" empty-text="暂无会话">
        <ConversationSidebar
          :conversations="conversations"
          :active-id="activeId"
          :loading="listLoading"
          :error="listError"
          @create="createConversation"
          @select="selectConversation"
          @rename="renameConversation"
          @remove="removeConversation"
        />
      </StateBlock>
    </div>

    <section class="sm-chat-main">
      <header class="sm-chat-toolbar">
        <ElButton class="sm-chat-sidebar-toggle" size="small" @click="sidebarOpen = !sidebarOpen">
          会话列表
        </ElButton>
        <h2 class="sm-chat-title">{{ conversations.find((item) => item.id === activeId)?.title ?? '智能客服' }}</h2>
        <span v-if="busy" class="sm-chat-streaming">
          <span class="sm-dot" aria-hidden="true" />
          正在回复（{{ turn.route ? routeLabel(turn.route) : '处理中' }}）…
        </span>
      </header>

      <StateBlock :loading="messagesLoading && !busy" :error="messagesError">
        <ChatThread
          v-if="activeId"
          :messages="messages"
          :turn="turn"
          @open-citations="onOpenCitations"
          @open-product="onOpenProduct"
          @retry="onRetry"
        />
      </StateBlock>

      <ChatComposer :streaming="busy" :disabled="!activeId" @send="onSend" @stop="stop" @handoff="handoffVisible = true" />
    </section>

    <ElDrawer v-model="citationDrawerVisible" title="政策引用" direction="rtl" size="min(28rem, 100%)">
      <CitationPanel :citations="drawerCitations" />
    </ElDrawer>

    <ProductDetailDialog v-model="detailVisible" :product-id="detailProductId" />

    <HandoffDialog v-model="handoffVisible" :conversation-id="activeId" />
  </div>
</template>

<style scoped>
.sm-chat {
  display: flex;
  height: calc(100vh - 49px);
  background: var(--sm-bg);
}

.sm-chat-sidebar {
  flex: none;
  background: var(--sm-surface);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.sm-chat-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--sm-surface);
}

.sm-chat-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--sm-border);
}

.sm-chat-title {
  margin: 0;
  font-size: 15px;
}

.sm-chat-streaming {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--sm-primary-dark);
}

.sm-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--sm-primary);
  animation: sm-pulse 1s infinite ease-in-out;
}

@keyframes sm-pulse {
  0%,
  100% {
    opacity: 0.3;
  }
  50% {
    opacity: 1;
  }
}

.sm-chat-sidebar-toggle {
  display: none;
}

@media (max-width: 768px) {
  .sm-chat {
    height: calc(100vh - 45px);
  }

  .sm-chat-sidebar {
    display: none;
  }

  .sm-chat-sidebar-open {
    display: flex;
    position: fixed;
    inset: 45px auto 0 0;
    z-index: 30;
    width: min(20rem, 86vw);
    box-shadow: 0 0 24px rgb(0 0 0 / 18%);
  }

  .sm-chat-sidebar-toggle {
    display: inline-flex;
  }
}
</style>
