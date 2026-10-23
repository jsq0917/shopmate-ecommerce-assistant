<script setup lang="ts">
/**
 * 消费者聊天页：会话管理 + SSE 流式回答 + 工具状态 + 商品卡片 + 引用侧栏。
 *
 * 约束：
 * - 会话/消息只经 REST 与 SSE 获取，不直连任何存储；
 * - 断线/失败有明确提示，半截回答标记“未完成”；
 * - 不展示 token、trace_id 或任何内部字段；
 * - 人工客服回复写入同一会话，页面用低频轮询把新消息并进线程（不打断正在生成的回答）。
 */

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElButton, ElDrawer, ElPopover } from 'element-plus'

import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatThread from '@/components/chat/ChatThread.vue'
import CitationPanel from '@/components/chat/CitationPanel.vue'
import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import GenerationParamsPanel from '@/components/chat/GenerationParamsPanel.vue'
import KnowledgeBaseSelect from '@/components/chat/KnowledgeBaseSelect.vue'
import HandoffDialog from '@/components/chat/HandoffDialog.vue'
import ProductDetailDialog from '@/components/catalog/ProductDetailDialog.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { conversationsApi, generationApi, knowledgeBasesApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { ChatMessageView } from '@/components/chat/MessageBubble.vue'
import type {
  ConversationGenerationParams,
  ConversationItem,
  GenerationDefaults,
  KnowledgeBaseOption,
  MessageCitation,
  MessageItem,
  ProductCardData,
} from '@/api/types'
import { useChatStream } from '@/composables/useChatStream'
import { routeLabel } from '@/utils/format'

defineOptions({ name: 'ChatView' })

const POLL_INTERVAL_MS = 8000

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

// 会话级知识库多选（stage 18）：空数组 = 不限制，检索全部可见知识库。
const kbOptions = ref<KnowledgeBaseOption[]>([])
const kbLoading = ref(false)
const kbSaving = ref(false)
const selectedKbIds = ref<string[]>([])
const kbError = ref<string | null>(null)

// 会话级推理参数（stage 19）：temperature / top_p / max_tokens / history_turns。
// 草稿由本页持有，控件拖动只更新草稿，提交点（松手/失焦）才 PATCH；保存成功以服务端
// 返回为准，失败回滚到服务端值并提示。未覆盖的字段用服务端默认值展示生效值。
const generationDefaults = ref<GenerationDefaults | null>(null)
const generationDraft = ref<ConversationGenerationParams>({})
const generationSaving = ref(false)
const generationError = ref<string | null>(null)

async function loadKnowledgeBases(): Promise<void> {
  kbLoading.value = true
  try {
    const data = await knowledgeBasesApi.list()
    kbOptions.value = data.items
    // 首次加载把当前会话的选择同步过来（旧会话没有该字段时按「全部」处理）。
    selectedKbIds.value = activeConversation.value?.knowledge_base_ids ?? []
  } catch {
    // 知识库列表失败不影响聊天本身：多选置灰，检索仍按「全部」进行。
    kbOptions.value = []
  } finally {
    kbLoading.value = false
  }
}

async function onKnowledgeBasesChange(ids: string[]): Promise<void> {
  const id = activeId.value
  if (!id) return
  kbError.value = null
  const previous = selectedKbIds.value
  selectedKbIds.value = ids
  kbSaving.value = true
  try {
    const updated = await conversationsApi.updateKnowledgeBases(id, ids)
    conversations.value = conversations.value.map((item) => (item.id === id ? updated : item))
    selectedKbIds.value = updated.knowledge_base_ids
  } catch (caught) {
    selectedKbIds.value = previous
    kbError.value = toApiError(caught).message
  } finally {
    kbSaving.value = false
  }
}

async function loadGenerationDefaults(): Promise<void> {
  try {
    generationDefaults.value = await generationApi.defaults()
    generationError.value = null
  } catch {
    // 默认值拉取失败只禁用参数面板，不影响聊天本身（参数按服务端默认执行）。
    generationDefaults.value = null
    generationError.value = '推理参数默认值加载失败，参数面板暂不可用。'
  }
}

/** 拖动过程中的实时更新：只改草稿，不发请求（提交点才 PATCH）。 */
function onGenerationParamsUpdate(params: ConversationGenerationParams): void {
  generationDraft.value = params
}

async function onGenerationParamsChange(params: ConversationGenerationParams): Promise<void> {
  const id = activeId.value
  if (!id) return
  generationError.value = null
  generationSaving.value = true
  try {
    const updated = await conversationsApi.updateGenerationParams(id, params)
    conversations.value = conversations.value.map((item) => (item.id === id ? updated : item))
    generationDraft.value = { ...updated.generation_params }
  } catch (caught) {
    // 失败回滚到服务端存储值：换一个新对象引用，让 watch 把面板同步回去。
    conversations.value = conversations.value.map((item) =>
      item.id === id ? { ...item, generation_params: { ...(item.generation_params ?? {}) } } : item,
    )
    generationDraft.value = { ...(activeConversation.value?.generation_params ?? {}) }
    generationError.value = toApiError(caught).message
  } finally {
    generationSaving.value = false
  }
}

const busy = computed(() => turn.value.active)
const activeConversation = computed(
  () => conversations.value.find((item) => item.id === activeId.value) ?? null,
)

/** 切换会话 / 保存成功后，把面板草稿同步成服务端存储的覆盖值。 */
watch(
  activeConversation,
  (conversation) => {
    generationDraft.value = { ...(conversation?.generation_params ?? {}) }
  },
  { immediate: true },
)
const activeTitle = computed(() => activeConversation.value?.title ?? '智能客服')
const showWelcome = computed(() => !messages.value.length && !busy.value)

const SUGGESTIONS: Array<{ icon: string; title: string; text: string }> = [
  {
    icon: '🎧',
    title: '按预算挑耳机',
    text: '预算 300 元以内，推荐一款适合通勤的降噪耳机',
  },
  {
    icon: '📦',
    title: '查订单物流',
    text: '订单 SM-2026-00025 的物流到哪了',
  },
  {
    icon: '↩️',
    title: '退货规则',
    text: '七天无理由退货是怎么规定的？',
  },
  {
    icon: '🧑‍💻',
    title: '转人工客服',
    text: '我要转人工',
  },
]

const CAPABILITIES = [
  { icon: '🛍️', text: '按预算和场景推荐商品，价格库存实时来自商品系统' },
  { icon: '📦', text: '查订单状态与物流节点，只返回你自己的订单' },
  { icon: '📄', text: '政策问答附文档、章节与生效日期，可溯源' },
  { icon: '🤝', text: '售后与投诉可一键转人工，保留完整上下文' },
]

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
    productCards: item.product_cards ?? [],
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
  selectedKbIds.value = conversations.value.find((item) => item.id === id)?.knowledge_base_ids ?? []
  kbError.value = null
  resetTurn()
  await loadMessages(id)
}

async function createConversation(): Promise<void> {
  if (turn.value.active) return
  // 连点「新对话」不应堆出一串空会话：当前会话本来就空时直接复用它。
  if (activeId.value && messages.value.length === 0) {
    sidebarOpen.value = false
    resetTurn()
    return
  }
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

/** 人工客服回复没有推送通道，用低频轮询把新消息并进线程。 */
async function pollNewMessages(): Promise<void> {
  if (!activeId.value || turn.value.active || document.hidden) return
  try {
    const data = await conversationsApi.messages(activeId.value, { limit: 100 })
    if (data.items.length !== messages.value.length) {
      messages.value = data.items.map(toView)
    }
  } catch {
    // 轮询失败不打扰用户，下一轮会重试。
  }
}

let pollTimer: number | undefined

onMounted(() => {
  void loadConversations()
  void loadKnowledgeBases()
  void loadGenerationDefaults()
  pollTimer = window.setInterval(() => void pollNewMessages(), POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer)
})
</script>

<template>
  <div class="sm-chat">
    <aside class="sm-chat-sidebar" :class="{ 'sm-chat-sidebar-open': sidebarOpen }">
      <div class="sm-sidebar-head">
        <span class="sm-sidebar-title">对话</span>
        <ElButton size="small" type="primary" plain @click="createConversation">+ 新对话</ElButton>
      </div>
      <StateBlock
        :loading="listLoading"
        :error="listError"
        :empty="!listLoading && !listError && !conversations.length"
        empty-text="暂无会话"
      >
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
    </aside>

    <section class="sm-chat-main">
      <header class="sm-chat-toolbar">
        <ElButton class="sm-chat-sidebar-toggle" size="small" @click="sidebarOpen = !sidebarOpen">
          会话
        </ElButton>
        <div class="sm-chat-heading">
          <h2 class="sm-chat-title">{{ activeTitle }}</h2>
          <span v-if="busy" class="sm-chat-streaming">
            <span class="sm-dot" aria-hidden="true" />
            {{ turn.route ? routeLabel(turn.route) : '正在思考' }}…
          </span>
          <span v-else class="sm-chat-status">在线 · 平均 1 秒内响应</span>
        </div>
        <div class="sm-chat-tools">
          <KnowledgeBaseSelect
            :options="kbOptions"
            :model-value="selectedKbIds"
            :disabled="!activeId || busy"
            :loading="kbLoading || kbSaving"
            @change="onKnowledgeBasesChange"
          />
          <ElPopover placement="bottom-end" trigger="click" :width="460">
            <template #reference>
              <ElButton
                size="small"
                text
                type="primary"
                data-testid="generation-params-trigger"
                :disabled="!activeId || !generationDefaults"
              >
                参数
              </ElButton>
            </template>
            <!--
              必须等「会话已选 + 默认值已就绪」再挂载面板：Element Plus 的 InputNumber 只在
              onMounted 时写一次 aria-disabled，若此刻面板因缺少会话/默认值而被禁用，该属性会
              永久停在 true（实际 disabled 已是 false），读屏与自动化都会误判控件不可用。
            -->
            <GenerationParamsPanel
              v-if="generationDefaults && activeId"
              :model-value="generationDraft"
              :defaults="generationDefaults"
              :disabled="!activeId || busy"
              :loading="generationSaving"
              @update:model-value="onGenerationParamsUpdate"
              @change="onGenerationParamsChange"
            />
          </ElPopover>
          <ElButton size="small" text type="primary" @click="handoffVisible = true">转人工</ElButton>
        </div>
      </header>
      <p v-if="kbError" class="sm-chat-kb-error" role="alert">{{ kbError }}</p>
      <p v-if="generationError" class="sm-chat-kb-error" role="alert">{{ generationError }}</p>

      <div v-if="showWelcome" class="sm-welcome">
        <div class="sm-welcome-head">
          <span class="sm-welcome-mark">SM</span>
          <div>
            <h1 class="sm-welcome-title">你好，我是 ShopMate</h1>
            <p class="sm-welcome-sub">挑商品、查订单、问售后，都可以直接问我。价格和库存来自实时数据。</p>
          </div>
        </div>

        <div class="sm-suggestions">
          <button
            v-for="item in SUGGESTIONS"
            :key="item.title"
            type="button"
            class="sm-suggestion"
            @click="onSend(item.text)"
          >
            <span class="sm-suggestion-icon">{{ item.icon }}</span>
            <span class="sm-suggestion-body">
              <strong>{{ item.title }}</strong>
              <small>{{ item.text }}</small>
            </span>
          </button>
        </div>

        <ul class="sm-capabilities">
          <li v-for="item in CAPABILITIES" :key="item.text">
            <span aria-hidden="true">{{ item.icon }}</span>{{ item.text }}
          </li>
        </ul>
      </div>

      <StateBlock v-else :loading="messagesLoading && !busy" :error="messagesError">
        <ChatThread
          v-if="activeId"
          :messages="messages"
          :turn="turn"
          @open-citations="onOpenCitations"
          @open-product="onOpenProduct"
          @retry="onRetry"
        />
      </StateBlock>

      <ChatComposer
        :streaming="busy"
        :disabled="!activeId"
        @send="onSend"
        @stop="stop"
        @handoff="handoffVisible = true"
      />
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
  flex: 1;
  min-height: 0;
  background: var(--sm-bg);
}

.sm-chat-sidebar {
  flex: none;
  width: 264px;
  background: var(--sm-surface);
  border-right: 1px solid var(--sm-border);
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.sm-sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 14px 8px;
}

.sm-sidebar-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--sm-text-tertiary);
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
  padding: 12px 20px;
  border-bottom: 1px solid var(--sm-border);
  background: rgb(255 255 255 / 90%);
  backdrop-filter: blur(10px);
}

.sm-chat-heading {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.sm-chat-title {
  margin: 0;
  font-size: 15px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sm-chat-status {
  font-size: 11px;
  color: var(--sm-text-tertiary);
}

.sm-chat-streaming {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--sm-primary-dark);
}

.sm-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--sm-primary);
  animation: sm-pulse 1s infinite ease-in-out;
}

@keyframes sm-pulse {
  0%,
  100% {
    opacity: 0.25;
    transform: scale(0.85);
  }
  50% {
    opacity: 1;
    transform: scale(1);
  }
}

.sm-chat-toolbar > :last-child {
  margin-left: auto;
}

/* ---- 欢迎屏 -------------------------------------------------------- */

.sm-welcome {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 36px 32px 20px;
  background:
    radial-gradient(760px 320px at 18% -10%, rgb(59 91 253 / 8%), transparent 70%),
    radial-gradient(620px 260px at 88% 4%, rgb(154 107 255 / 7%), transparent 70%),
    var(--sm-surface);
}

.sm-welcome-head {
  display: flex;
  align-items: center;
  gap: 14px;
  max-width: 720px;
}

.sm-welcome-mark {
  display: grid;
  place-items: center;
  width: 48px;
  height: 48px;
  border-radius: 15px;
  background: var(--sm-gradient);
  color: #fff;
  font-weight: 800;
  font-size: 15px;
  box-shadow: 0 8px 22px rgb(59 91 253 / 28%);
  flex: none;
}

.sm-welcome-title {
  margin: 0;
  font-size: 24px;
  font-weight: 750;
  letter-spacing: -0.02em;
}

.sm-welcome-sub {
  margin: 4px 0 0;
  color: var(--sm-text-secondary);
  font-size: 13px;
}

.sm-suggestions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  max-width: 720px;
  margin: 22px 0 18px;
}

.sm-suggestion {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--sm-radius);
  border: 1px solid var(--sm-border);
  background: var(--sm-surface);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
}

.sm-suggestion:hover {
  border-color: #c5ceff;
  transform: translateY(-1px);
  box-shadow: var(--sm-shadow-md);
}

.sm-suggestion-icon {
  font-size: 18px;
  line-height: 1.3;
}

.sm-suggestion-body {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.sm-suggestion-body strong {
  font-size: 13px;
}

.sm-suggestion-body small {
  font-size: 11px;
  color: var(--sm-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sm-capabilities {
  list-style: none;
  margin: 0;
  padding: 14px 0 0;
  border-top: 1px dashed var(--sm-border);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 20px;
  max-width: 720px;
  color: var(--sm-text-secondary);
  font-size: 12px;
}

.sm-capabilities li {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.sm-chat-sidebar-toggle {
  display: none;
}

@media (max-width: 768px) {
  .sm-chat {
    min-height: 0;
  }

  .sm-chat-sidebar {
    display: none;
  }

  .sm-chat-sidebar-open {
    display: flex;
    position: fixed;
    inset: 52px auto 0 0;
    z-index: 30;
    width: min(20rem, 86vw);
    box-shadow: var(--sm-shadow-lg);
  }

  .sm-chat-sidebar-toggle {
    display: inline-flex;
  }

  .sm-welcome {
    padding: 22px 16px 16px;
  }

  .sm-suggestions,
  .sm-capabilities {
    grid-template-columns: 1fr;
  }

  .sm-welcome-title {
    font-size: 20px;
  }
}
</style>
