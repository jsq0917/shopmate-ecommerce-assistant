import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MessageBubble, { type ChatMessageView } from '@/components/chat/MessageBubble.vue'
import { ApiError } from '@/api/errors'
import { citationFixture, productCardFixture } from '@/test/factories'

function messageFixture(overrides: Partial<ChatMessageView> = {}): ChatMessageView {
  return {
    key: 'm-1',
    role: 'assistant',
    content: '这款耳机支持主动降噪。',
    citations: [],
    risk: {},
    route: 'product_fact',
    finishReason: 'stop',
    isComplete: true,
    createdAt: '2026-03-01T09:05:00Z',
    ...overrides,
  }
}

describe('MessageBubble', () => {
  it('用户消息只展示文本，不带助手头部', () => {
    const wrapper = mount(MessageBubble, {
      props: { message: messageFixture({ role: 'user', content: '你好' }) },
    })
    expect(wrapper.text()).toContain('你好')
    expect(wrapper.text()).not.toContain('ShopMate 助手')
    expect(wrapper.classes()).toContain('sm-message-user')
  })

  it('助手消息展示路由与回答时间', () => {
    const wrapper = mount(MessageBubble, { props: { message: messageFixture() } })
    expect(wrapper.text()).toContain('ShopMate 助手')
    expect(wrapper.text()).toContain('商品详情')
    expect(wrapper.text()).toContain('回答时间')
  })

  it('中高风险展示风险标签，低风险不展示', () => {
    const high = mount(MessageBubble, {
      props: {
        message: messageFixture({
          risk: { risk_level: 'high', primary_reason_code: 'COMPLAINT' },
        }),
      },
    })
    expect(high.text()).toContain('高风险')
    expect(high.text()).toContain('投诉')

    const low = mount(MessageBubble, {
      props: { message: messageFixture({ risk: { risk_level: 'low' } }) },
    })
    expect(low.text()).not.toContain('低风险')
  })

  it('finish_reason 状态有明确标识', () => {
    const refusal = mount(MessageBubble, {
      props: { message: messageFixture({ finishReason: 'refusal', isComplete: false }) },
    })
    expect(refusal.text()).toContain('已拒答')
    expect(refusal.text()).toContain('未完成')

    const handoff = mount(MessageBubble, {
      props: { message: messageFixture({ finishReason: 'handoff' }) },
    })
    expect(handoff.text()).toContain('已转人工')
  })

  it('引用按钮展示数量并触发事件', async () => {
    const citations = [citationFixture(), citationFixture({ citation_id: 'cit-2' })]
    const wrapper = mount(MessageBubble, {
      props: { message: messageFixture({ citations }) },
    })
    const button = wrapper.find('button')
    expect(button.text()).toContain('查看引用（2）')
    await button.trigger('click')
    expect(wrapper.emitted('open-citations')?.[0]?.[0]).toHaveLength(2)
  })

  it('商品卡片渲染价格与库存标签', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: messageFixture({
          content: '',
          productCards: [productCardFixture()],
        }),
      },
    })
    expect(wrapper.text()).toContain('¥299.00')
    expect(wrapper.text()).toContain('有货')
  })

  it('失败消息展示错误与可重试按钮', async () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: messageFixture({
          isComplete: false,
          finishReason: 'error',
          content: '',
          error: new ApiError({
            code: 'NETWORK_ERROR',
            message: '网络连接失败，请检查网络后重试。',
            status: 0,
            retryable: true,
          }),
        }),
      },
    })
    expect(wrapper.text()).toContain('网络连接失败')
    const retry = wrapper.findAll('button').find((btn) => btn.text() === '重试')
    expect(retry).toBeTruthy()
    await retry!.trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('仅有工具进行中时展示占位文案', () => {
    const wrapper = mount(MessageBubble, {
      props: {
        message: messageFixture({
          content: '',
          toolStatuses: [{ toolName: 'search_products', status: 'started', displayMessage: null, errorCode: null }],
        }),
      },
    })
    expect(wrapper.text()).toContain('正在处理')
    expect(wrapper.text()).toContain('商品搜索')
  })
})
