import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import ChatView from '@/views/ChatView.vue'
import { networkError } from '@/api/errors'
import { ApiError } from '@/api/errors'
import {
  CONVERSATION_ID,
  MESSAGE_ID,
  conversationFixture,
  messageFixture,
  sseEvent,
} from '@/test/factories'

vi.mock('@/api/endpoints', () => ({
  conversationsApi: {
    list: vi.fn(),
    create: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    messages: vi.fn(),
  },
  chatApi: { stream: vi.fn() },
  productsApi: { detail: vi.fn() },
  handoffApi: { list: vi.fn(), get: vi.fn(), create: vi.fn() },
}))

const { conversationsApi, chatApi } = await import('@/api/endpoints')

/** 一轮完整 SSE 事件序列。 */
function happyEvents() {
  return [
    sseEvent('meta', { route: 'product_fact' }, 1),
    sseEvent('tool_status', { tool_name: 'search_products', status: 'started', display_message: '正在检索商品' }, 2),
    sseEvent('tool_status', { tool_name: 'search_products', status: 'succeeded', display_message: null, error_code: null }, 3),
    sseEvent('delta', { message_id: MESSAGE_ID, index: 0, text: '这款耳机' }, 4),
    sseEvent('delta', { message_id: MESSAGE_ID, index: 1, text: '支持主动降噪。' }, 5),
    sseEvent('done', { message_id: MESSAGE_ID, finish_reason: 'stop', persisted: true, message_is_complete: true }, 6),
  ]
}

async function mountChat() {
  const wrapper = mount(ChatView)
  await flushPromises()
  await flushPromises()
  return wrapper
}

/** 在输入框输入并回车发送。 */
async function sendMessage(wrapper: Awaited<ReturnType<typeof mountChat>>, text: string) {
  const textarea = wrapper.find('textarea')
  await textarea.setValue(text)
  await textarea.trigger('keydown.enter')
  await flushPromises()
  await flushPromises()
}

describe('ChatView 集成', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    if (!crypto.randomUUID) {
      (crypto as { randomUUID: () => string }).randomUUID = () => 'test-uuid'
    }
    vi.mocked(conversationsApi.list).mockResolvedValue({
      items: [conversationFixture()],
      next_cursor: null,
    })
    vi.mocked(conversationsApi.messages).mockResolvedValue({
      items: [messageFixture({ role: 'user', content: '有没有降噪耳机' })],
      next_cursor: null,
    })
  })

  it('挂载后加载会话并展示首条消息', async () => {
    const wrapper = await mountChat()
    expect(conversationsApi.list).toHaveBeenCalled()
    expect(conversationsApi.messages).toHaveBeenCalledWith(CONVERSATION_ID, { limit: 100 })
    expect(wrapper.text()).toContain('有没有降噪耳机')
    expect(wrapper.text()).toContain('耳机咨询')
  })

  it('完整流式对话：工具状态 -> 增量文本 -> done，最终以服务端历史为准', async () => {
    vi.mocked(chatApi.stream).mockImplementation(async (_params, consumer) => {
      for (const event of happyEvents()) consumer.onEvent(event)
    })
    // 第二轮 messages 返回含助手回复的历史
    vi.mocked(conversationsApi.messages).mockResolvedValueOnce({
      items: [messageFixture({ role: 'user', content: '有没有降噪耳机' })],
      next_cursor: null,
    })
    vi.mocked(conversationsApi.messages).mockResolvedValueOnce({
      items: [
        messageFixture({ role: 'user', content: '有没有降噪耳机' }),
        messageFixture({ content: '这款耳机支持主动降噪。' }),
      ],
      next_cursor: null,
    })

    const wrapper = await mountChat()
    await sendMessage(wrapper, '有没有降噪耳机')

    // 流参数带幂等 client_message_id
    expect(chatApi.stream).toHaveBeenCalledTimes(1)
    const [params] = vi.mocked(chatApi.stream).mock.calls[0]
    expect(params.conversation_id).toBe(CONVERSATION_ID)
    expect(params.message).toBe('有没有降噪耳机')
    expect(params.client_message_id).toBeTruthy()

    // 发送后重新加载历史并展示服务端持久化的回复
    expect(conversationsApi.messages).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('这款耳机支持主动降噪。')
    expect(wrapper.text()).toContain('商品详情')
  })

  it('断线（NETWORK_ERROR）后重新加载历史，不展示半截回答', async () => {
    vi.mocked(chatApi.stream).mockRejectedValue(networkError(new TypeError('Failed to fetch')))

    const wrapper = await mountChat()
    await sendMessage(wrapper, '你好')

    expect(conversationsApi.messages).toHaveBeenCalledTimes(2)
    // 断线后回到历史视图，不残留流式气泡
    expect(wrapper.text()).toContain('有没有降噪耳机')
    expect(wrapper.text()).not.toContain('正在回复')
  })

  it('重复提交（REQUEST_IN_PROGRESS）按历史 reload 处理', async () => {
    vi.mocked(chatApi.stream).mockRejectedValue(
      new ApiError({
        code: 'REQUEST_IN_PROGRESS',
        message: '上一条消息正在处理，请稍候。',
        status: 409,
      }),
    )

    const wrapper = await mountChat()
    await sendMessage(wrapper, '在吗')

    expect(conversationsApi.messages).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('有没有降噪耳机')
  })

  it('error 事件（服务端业务错误）后重新加载历史', async () => {
    vi.mocked(chatApi.stream).mockImplementation(async (_params, consumer) => {
      consumer.onEvent(
        sseEvent(
          'error',
          {
            error_code: 'UPSTREAM_UNAVAILABLE',
            user_message: '服务暂时不可用，请稍后重试或转人工。',
            retryable: true,
            retry_after_ms: null,
            partial_message_id: null,
            partial_persisted: false,
          },
          2,
        ),
      )
    })

    const wrapper = await mountChat()
    await sendMessage(wrapper, '查订单')

    expect(conversationsApi.messages).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('有没有降噪耳机')
  })

  it('用户停止生成后回到历史视图', async () => {
    vi.mocked(chatApi.stream).mockImplementation(async (params, consumer) => {
      consumer.onEvent(sseEvent('delta', { message_id: MESSAGE_ID, index: 0, text: '半句' }, 1))
      // 模拟流进行中：直到 abort 才以 AbortError 结束
      await new Promise<void>((_resolve, reject) => {
        if (params.signal?.aborted) {
          reject(new DOMException('The stream was aborted.', 'AbortError'))
          return
        }
        params.signal?.addEventListener('abort', () => {
          reject(new DOMException('The stream was aborted.', 'AbortError'))
        })
      })
    })

    const wrapper = await mountChat()
    const textarea = wrapper.find('textarea')
    await textarea.setValue('长问题')
    await textarea.trigger('keydown.enter')
    await flushPromises()

    // 流进行中：展示“正在回复”
    expect(wrapper.text()).toContain('正在回复')

    const stopButton = wrapper.findAll('button').find((btn) => btn.text() === '停止生成')
    await stopButton!.trigger('click')
    await flushPromises()
    await flushPromises()

    expect(conversationsApi.messages).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('正在回复')
  })

  it('会话列表为空时自动创建新会话', async () => {
    vi.mocked(conversationsApi.list).mockResolvedValue({ items: [], next_cursor: null })
    vi.mocked(conversationsApi.create).mockResolvedValue(
      conversationFixture({ id: CONVERSATION_ID, title: '新会话' }),
    )

    const wrapper = await mountChat()
    expect(conversationsApi.create).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('新会话')
  })

  it('会话列表加载失败展示错误态', async () => {
    vi.mocked(conversationsApi.list).mockRejectedValue(networkError())
    const wrapper = await mountChat()
    expect(wrapper.text()).toContain('网络连接失败')
  })

  it('发送中禁用输入框', async () => {
    vi.mocked(chatApi.stream).mockImplementation(() => new Promise<void>(() => {}))
    const wrapper = await mountChat()
    const textarea = wrapper.find('textarea')
    await textarea.setValue('问题')
    await textarea.trigger('keydown.enter')
    await flushPromises()
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    expect(wrapper.text()).toContain('停止生成')
  })
})
