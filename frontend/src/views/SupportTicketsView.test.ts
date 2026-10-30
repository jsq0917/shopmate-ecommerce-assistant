import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'

import SupportTicketsView from '@/views/SupportTicketsView.vue'
import { networkError } from '@/api/errors'
import { supportTicketFixture } from '@/test/factories'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/api/endpoints', () => ({
  supportApi: { tickets: vi.fn(), refunds: vi.fn(), patchTicket: vi.fn() },
}))

const { supportApi } = await import('@/api/endpoints')

async function mountView() {
  const wrapper = mount(SupportTicketsView)
  await flushPromises()
  return wrapper
}

function bulkButton(wrapper: Awaited<ReturnType<typeof mountView>>) {
  const button = wrapper.findAll('button').find((btn) => btn.text().includes('批量驳回'))
  if (!button) throw new Error('没有找到批量驳回按钮')
  return button
}

describe('SupportTicketsView（工单队列）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(supportApi.tickets).mockResolvedValue({
      items: [supportTicketFixture()],
      next_offset: null,
    })
    vi.mocked(supportApi.refunds).mockResolvedValue({ items: [], next_offset: null } as never)
    vi.mocked(supportApi.patchTicket).mockResolvedValue({
      ticket_id: 'ticket-1',
      status: 'closed',
      assigned_to_masked: null,
      updated_at: '2026-03-01T09:20:00Z',
      request_id: 'req-1',
    } as never)
  })

  it('加载并展示工单（脱敏用户、风险、等待时间）', async () => {
    const wrapper = await mountView()
    expect(supportApi.tickets).toHaveBeenCalledWith({
      status: undefined,
      risk_level: undefined,
      transcript: 'available',
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

  it('勾选后带上 transcript=all，并给会话已删除的工单打标', async () => {
    vi.mocked(supportApi.tickets).mockResolvedValue({
      items: [supportTicketFixture({ transcript_available: false })],
      next_offset: null,
    })
    const wrapper = await mountView()
    const toggle = wrapper.find('.sm-toggle input')
    await toggle.setValue(true)
    await flushPromises()

    expect(supportApi.tickets).toHaveBeenLastCalledWith({
      status: undefined,
      risk_level: undefined,
      transcript: 'all',
      limit: 50,
    })
    expect(wrapper.text()).toContain('会话已删除')
    expect(wrapper.text()).toContain('其中 1 条会话已删除')
  })

  it('点击卡片跳转工单详情', async () => {
    const wrapper = await mountView()
    const card = wrapper.find('.sm-ticket-card')
    await card.trigger('click')
    expect(push).toHaveBeenCalledWith('/support/tickets/ticket-1')
  })

  it('「待处理工单」「高风险工单」两个统计卡已下线，退款计数保留', async () => {
    const wrapper = await mountView()
    expect(wrapper.text()).not.toContain('待处理工单')
    expect(wrapper.text()).not.toContain('高风险工单')
    expect(wrapper.text()).toContain('待审核退款')
    // 数据没有被删除：状态与风险筛选仍然可用
    expect(wrapper.text()).toContain('全部状态')
    expect(wrapper.text()).toContain('全部风险')
  })

  it('未选中工单时批量驳回按钮禁用', async () => {
    const wrapper = await mountView()
    expect(bulkButton(wrapper).attributes('disabled')).toBeDefined()
  })

  it('多选后一次性驳回：逐条提交关闭原因，成功后清空选择并刷新', async () => {
    vi.mocked(supportApi.tickets).mockResolvedValue({
      items: [
        supportTicketFixture({ ticket_id: 'ticket-1' }),
        supportTicketFixture({ ticket_id: 'ticket-2', status: 'assigned' }),
      ],
      next_offset: null,
    })
    const prompt = vi
      .spyOn(ElMessageBox, 'prompt')
      .mockResolvedValue({ value: '  重复提交  ' } as never)
    const success = vi.spyOn(ElMessage, 'success').mockImplementation(() => ({}) as never)

    const wrapper = await mountView()
    const boxes = wrapper.findAll('.sm-ticket-check input')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    expect(wrapper.text()).toContain('已选 2 条')

    await bulkButton(wrapper).trigger('click')
    await flushPromises()

    expect(prompt).toHaveBeenCalledTimes(1)
    expect(prompt.mock.calls[0][0]).toContain('2 条工单')
    expect(supportApi.patchTicket).toHaveBeenCalledTimes(2)
    expect(supportApi.patchTicket).toHaveBeenCalledWith('ticket-1', {
      action: 'archive',
      close_reason: '批量驳回：重复提交',
    })
    expect(supportApi.patchTicket).toHaveBeenCalledWith('ticket-2', {
      action: 'archive',
      close_reason: '批量驳回：重复提交',
    })
    expect(success).toHaveBeenCalledWith('已驳回 2 条工单')
    // 刷新后重新加载列表，选择被清空
    expect(supportApi.tickets).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).not.toContain('已选 2 条')
  })

  it('取消填写原因时不提交任何驳回请求', async () => {
    const prompt = spyOnPromptCancel()
    const wrapper = await mountView()
    await wrapper.findAll('.sm-ticket-check input')[0].setValue(true)

    await bulkButton(wrapper).trigger('click')
    await flushPromises()

    expect(prompt).toHaveBeenCalledTimes(1)
    expect(supportApi.patchTicket).not.toHaveBeenCalled()
    // 选择保留，方便用户重新操作
    expect(wrapper.text()).toContain('已选 1 条')
  })

  it('部分失败时如实反馈并列出失败工单', async () => {
    vi.mocked(supportApi.tickets).mockResolvedValue({
      items: [
        supportTicketFixture({ ticket_id: 'ticket-1' }),
        supportTicketFixture({ ticket_id: 'ticket-2' }),
      ],
      next_offset: null,
    })
    vi.mocked(supportApi.patchTicket).mockImplementation(((ticketId: string) =>
      ticketId === 'ticket-2'
        ? Promise.reject(networkError())
        : Promise.resolve({ ticket_id: ticketId })) as never)
    vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue({ value: '信息不足' } as never)
    const warning = vi.spyOn(ElMessage, 'warning').mockImplementation(() => ({}) as never)

    const wrapper = await mountView()
    const boxes = wrapper.findAll('.sm-ticket-check input')
    await boxes[0].setValue(true)
    await boxes[1].setValue(true)
    await bulkButton(wrapper).trigger('click')
    await flushPromises()

    expect(warning).toHaveBeenCalledWith('已驳回 1 条，1 条失败，失败明细见列表上方')
    expect(wrapper.text()).toContain('部分工单驳回失败')
    expect(wrapper.text()).toContain('ticket-2')
    expect(wrapper.text()).toContain('网络连接失败')
  })

  it('已关闭 / 已解决的工单不能勾选驳回', async () => {
    vi.mocked(supportApi.tickets).mockResolvedValue({
      items: [
        supportTicketFixture({ ticket_id: 'ticket-1', status: 'closed' }),
        supportTicketFixture({ ticket_id: 'ticket-2', status: 'resolved' }),
      ],
      next_offset: null,
    })
    const wrapper = await mountView()

    const boxes = wrapper.findAll('.sm-ticket-check input')
    expect(boxes[0].attributes('disabled')).toBeDefined()
    expect(boxes[1].attributes('disabled')).toBeDefined()
    // 没有可驳回项时不显示批量工具条
    expect(wrapper.text()).not.toContain('全选可驳回')
  })

  it('全选只覆盖可驳回的工单', async () => {
    vi.mocked(supportApi.tickets).mockResolvedValue({
      items: [
        supportTicketFixture({ ticket_id: 'ticket-1' }),
        supportTicketFixture({ ticket_id: 'ticket-2', status: 'closed' }),
        supportTicketFixture({ ticket_id: 'ticket-3', status: 'assigned' }),
      ],
      next_offset: null,
    })
    const wrapper = await mountView()

    const selectAll = wrapper.find('.sm-bulk-bar .el-checkbox input')
    await selectAll.setValue(true)
    expect(wrapper.text()).toContain('已选 2 条')
  })

  it('点击勾选框不会误跳转到工单详情', async () => {
    const wrapper = await mountView()
    push.mockClear()
    await wrapper.find('.sm-ticket-check').trigger('click')
    expect(push).not.toHaveBeenCalled()
  })
})

function spyOnPromptCancel() {
  return vi.spyOn(ElMessageBox, 'prompt').mockRejectedValue('cancel')
}
