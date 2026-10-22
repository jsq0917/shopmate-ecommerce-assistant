import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import SupportTicketsView from '@/views/SupportTicketsView.vue'
import { networkError } from '@/api/errors'
import { supportTicketFixture } from '@/test/factories'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/api/endpoints', () => ({
  supportApi: { tickets: vi.fn(), refunds: vi.fn() },
}))

const { supportApi } = await import('@/api/endpoints')

async function mountView() {
  const wrapper = mount(SupportTicketsView)
  await flushPromises()
  return wrapper
}

describe('SupportTicketsView（工单队列）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(supportApi.tickets).mockResolvedValue({
      items: [supportTicketFixture()],
      next_offset: null,
    })
    vi.mocked(supportApi.refunds).mockResolvedValue({ items: [], next_offset: null } as never)
  })

  it('加载并展示工单（脱敏用户、风险、等待时间）', async () => {
    const wrapper = await mountView()
    expect(supportApi.tickets).toHaveBeenCalledWith({
      status: undefined,
      risk_level: undefined,
      limit: 50,
    })
    expect(wrapper.text()).toContain('待处理')
    expect(wrapper.text()).toContain('中')
    expect(wrapper.text()).toContain('用户要求人工')
    expect(wrapper.text()).toContain('P2')
    expect(wrapper.text()).toContain('after_sales')
    expect(wrapper.text()).toContain('1 分钟')
    expect(wrapper.text()).toContain('用户 138****8888')
    // 不泄露完整手机号
    expect(wrapper.text()).not.toContain('13800138000')
  })

  it('空队列展示空态', async () => {
    vi.mocked(supportApi.tickets).mockResolvedValue({ items: [], next_offset: null })
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('当前没有需要处理的工单')
  })

  it('加载失败展示可重试错误态', async () => {
    vi.mocked(supportApi.tickets).mockRejectedValue(networkError())
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('网络连接失败')
    const retry = wrapper.find('button')
    await retry.trigger('click')
    await flushPromises()
    expect(supportApi.tickets).toHaveBeenCalledTimes(2)
  })

  it('点击卡片跳转工单详情', async () => {
    const wrapper = await mountView()
    const card = wrapper.find('.sm-ticket-card')
    await card.trigger('click')
    expect(push).toHaveBeenCalledWith('/support/tickets/ticket-1')
  })
})
