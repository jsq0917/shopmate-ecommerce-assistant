import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ChatThread from '@/components/chat/ChatThread.vue'
import MessageBubble from '@/components/chat/MessageBubble.vue'
import type { ChatMessageView } from '@/components/chat/MessageBubble.vue'
import { networkError } from '@/api/errors'
import type { TurnState } from '@/composables/useChatStream'

function idleTurn(): TurnState {
  return {
    active: false,
    route: null,
    toolStatuses: [],
    productCards: [],
    citations: [],
    text: '',
    messageId: null,
    finishReason: null,
    error: null,
    stopped: false,
    rejected: null,
  }
}

function history(count: number): ChatMessageView[] {
  return Array.from({ length: count }, (_, index) => ({
    key: `m-${index}`,
    role: index % 2 === 0 ? 'user' : 'assistant',
    content: `消息 ${index + 1}`,
    citations: [],
    risk: {},
    route: null,
    finishReason: 'stop',
    isComplete: true,
    createdAt: null,
    productCards: [],
  }))
}

/** jsdom 不做布局：手动给滚动元素注入可断言的几何值。 */
function stubGeometry(element: Element, scrollHeight: number, clientHeight: number): void {
  Object.defineProperty(element, 'scrollHeight', { value: scrollHeight, configurable: true })
  Object.defineProperty(element, 'clientHeight', { value: clientHeight, configurable: true })
}

const CONVERSATION = 'conv-1'

async function mountThread(props: {
  messages: ChatMessageView[]
  turn: TurnState
  conversationId?: string | null
}) {
  const wrapper = mount(ChatThread, {
    props: { conversationId: CONVERSATION, ...props },
  })
  // onMounted 的初始滚底含 nextTick：先让它完成，再注入几何与手动滚动，
  // 避免初始滚底的迟到续体覆盖测试设置的 scrollTop（jsdom 无布局，竞态可见）。
  await flushPromises()
  return wrapper
}

describe('ChatThread', () => {
  it('渲染全部历史消息与流式气泡', async () => {
    const wrapper = await mountThread({
      messages: history(3),
      turn: { ...idleTurn(), active: true, text: '流式回答' },
    })
    expect(wrapper.findAllComponents(MessageBubble)).toHaveLength(4)
    expect(wrapper.find('[data-testid="thinking-indicator"]').exists()).toBe(false)
  })

  it('空状态提示仅在没有任何消息与流时出现', async () => {
    const wrapper = await mountThread({ messages: [], turn: idleTurn() })
    expect(wrapper.find('.sm-thread-empty').exists()).toBe(true)
  })

  it('流已建立但尚无产出时显示“正在思考”指示器而不是空气泡', async () => {
    const wrapper = await mountThread({ messages: history(1), turn: idleTurn() })
    expect(wrapper.find('[data-testid="thinking-indicator"]').exists()).toBe(false)

    await wrapper.setProps({ turn: { ...idleTurn(), active: true } })
    expect(wrapper.find('[data-testid="thinking-indicator"]').exists()).toBe(true)
    expect(wrapper.findAllComponents(MessageBubble)).toHaveLength(1)

    const text = wrapper.findAllComponents(MessageBubble).length
    await wrapper.setProps({ turn: { ...idleTurn(), active: true, text: '第一个字' } })
    expect(wrapper.find('[data-testid="thinking-indicator"]').exists()).toBe(false)
    expect(wrapper.findAllComponents(MessageBubble)).toHaveLength(text + 1)
  })

  it('失败但无正文的 turn 仍然渲染错误气泡（可重试），不被思考指示器吞掉', async () => {
    const wrapper = await mountThread({
      messages: [],
      turn: { ...idleTurn(), active: false, error: networkError() },
    })
    expect(wrapper.find('[data-testid="thinking-indicator"]').exists()).toBe(false)
    const bubble = wrapper.findComponent(MessageBubble)
    expect(bubble.exists()).toBe(true)
    expect(bubble.props('message').error).not.toBeNull()
  })

  it('贴底时新内容自动跟随滚动；用户上翻后停止跟随', async () => {
    const wrapper = await mountThread({
      messages: history(5),
      turn: { ...idleTurn(), active: true, text: '流式' },
    })
    const element = wrapper.find('.sm-thread').element as HTMLElement
    stubGeometry(element, 3000, 500)

    // 贴底（距底 0px）：delta 到达应滚到底。
    element.scrollTop = 2500
    await element.dispatchEvent(new Event('scroll'))
    await wrapper.setProps({ turn: { ...idleTurn(), active: true, text: '流式加长' } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(element.scrollTop).toBe(3000)

    // 上翻到历史区（距底 2000px）：后续 delta 不再抢滚动位置。
    element.scrollTop = 500
    await element.dispatchEvent(new Event('scroll'))
    await wrapper.setProps({ turn: { ...idleTurn(), active: true, text: '流式继续加长' } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(element.scrollTop).toBe(500)

    // 回到底部附近（距底 40px < 80px 阈值）：恢复自动跟随。
    element.scrollTop = 2460
    await element.dispatchEvent(new Event('scroll'))
    await wrapper.setProps({ turn: { ...idleTurn(), active: true, text: '再次加长' } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(element.scrollTop).toBe(3000)
  })

  it('切换会话（conversationId 变化）强制滚底，即使用户此前在上方', async () => {
    const wrapper = await mountThread({ messages: history(5), turn: idleTurn() })
    const element = wrapper.find('.sm-thread').element as HTMLElement
    stubGeometry(element, 3000, 500)

    element.scrollTop = 500
    await element.dispatchEvent(new Event('scroll'))

    await wrapper.setProps({ conversationId: 'conv-2', messages: history(8) })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(element.scrollTop).toBe(3000)
  })

  it('同会话的历史刷新（messages 整体替换）不强制滚底，不打扰正在翻历史的用户', async () => {
    const wrapper = await mountThread({ messages: history(5), turn: idleTurn() })
    const element = wrapper.find('.sm-thread').element as HTMLElement
    stubGeometry(element, 3000, 500)

    element.scrollTop = 500
    await element.dispatchEvent(new Event('scroll'))

    // 每轮回答结束后的 loadMessages 就是这种替换：不允许把用户拽回底部。
    // （history(4) 以 assistant 结尾，与真实历史刷新一致，不触发“新用户消息”规则。）
    await wrapper.setProps({ messages: [...history(5), ...history(4)] })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(element.scrollTop).toBe(500)
  })

  it('用户发送的新消息无条件滚底（发送意味着关注最新内容）', async () => {
    const wrapper = await mountThread({ messages: history(5), turn: idleTurn() })
    const element = wrapper.find('.sm-thread').element as HTMLElement
    stubGeometry(element, 3000, 500)

    element.scrollTop = 300
    await element.dispatchEvent(new Event('scroll'))

    const next = [...history(5), { ...history(1)[0], key: 'local-1', role: 'user' as const }]
    await wrapper.setProps({ messages: next })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(element.scrollTop).toBe(3000)
  })
})
