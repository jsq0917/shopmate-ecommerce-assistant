import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import SupportTicketDetailView from '@/views/SupportTicketDetailView.vue'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/errors'
import type { SupportTicketDetail } from '@/api/types'

const TRANSCRIPT_GONE = '该会话已被用户删除，无法查看聊天记录。'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ params: { ticketId: 'ticket-1' } }),
}))

vi.mock('@/api/endpoints', () => ({
  supportApi: {
    ticket: vi.fn(),
    conversation: vi.fn(),
    patchTicket: vi.fn(),
    reply: vi.fn(),
    qualityLabel: vi.fn(),
  },
}))

const { supportApi } = await import('@/api/endpoints')

function ticketFixture(overrides: Partial<SupportTicketDetail> = {}): SupportTicketDetail {
  return {
    ticket_id: 'ticket-1',
    status: 'open',
    risk_level: 'medium',
    primary_reason_code: 'USER_REQUESTS_HUMAN',
    reason_codes: ['USER_REQUESTS_HUMAN'],
    priority: 2,
    queue: 'after_sales',
    conversation_id: 'conversation-1',
    user_reference_masked: '用户 138****8888',
    assigned_to_masked: null,
    created_at: '2026-03-01T09:10:00Z',
    updated_at: '2026-03-01T09:12:00Z',
    waiting_seconds: 95,
    summary_redacted: '用户要求转人工（合成）',
    expected_response: '30 分钟内响应',
    transcript_available: true,
    assigned_to_me: false,
    ...overrides,
  }
}

const transcript = {
  conversation_id: 'conversation-1',
  title: '订单售后咨询',
  owner_reference_masked: '用户 138****8888',
  target_user_id: 'user-1',
  ticket_id: 'ticket-1',
  messages: [],
  tool_calls: [],
  handoff: { ticket_id: 'ticket-1', status: 'open', primary_reason_code: 'USER_REQUESTS_HUMAN' },
}

async function mountView() {
  // 视图用 auth store 取当前 user_id（用于「我是否接管人」的兜底判定），必须提供 pinia。
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { user_id: 'agent-1', role: 'support' } as never
  const wrapper = mount(SupportTicketDetailView, { global: { plugins: [pinia] } })
  await flushPromises()
  return wrapper
}

describe('SupportTicketDetailView（工单详情）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 「本机接管备忘」存在 sessionStorage，用例之间必须隔离，否则会串号。
    sessionStorage.clear()
    vi.mocked(supportApi.ticket).mockResolvedValue(ticketFixture())
    vi.mocked(supportApi.conversation).mockResolvedValue(transcript as never)
    vi.mocked(supportApi.patchTicket).mockResolvedValue({
      ticket_id: 'ticket-1',
      status: 'closed',
      assigned_to_masked: null,
      updated_at: '2026-03-01T09:20:00Z',
      request_id: 'req-1',
    } as never)
  })

  it('会话已删除时仍展示工单，并说明取证失败原因', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(ticketFixture({ transcript_available: false }))
    vi.mocked(supportApi.conversation).mockRejectedValue(
      new ApiError({ code: 'NOT_FOUND', message: TRANSCRIPT_GONE, status: 404, retryable: false }),
    )

    const wrapper = await mountView()

    // 工单元数据照常可见，不会被一次取证失败整页吞掉
    expect(wrapper.text()).toContain('ticket-1')
    expect(wrapper.text()).toContain('用户要求转人工')
    expect(wrapper.text()).toContain('该会话已被用户删除')
    // 会话没了就不能回复或打分
    expect(wrapper.text()).not.toContain('回复用户')
    expect(wrapper.text()).not.toContain('对 AI 回答打分')
    // 但可以归档
    expect(wrapper.text()).toContain('归档')
  })

  it('归档会带上必填原因调用状态机', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(ticketFixture({ transcript_available: false }))
    vi.mocked(supportApi.conversation).mockRejectedValue(
      new ApiError({ code: 'NOT_FOUND', message: TRANSCRIPT_GONE, status: 404, retryable: false }),
    )
    const wrapper = await mountView()

    const archiveButton = wrapper.findAll('button').find((node) => node.text() === '归档')
    expect(archiveButton).toBeTruthy()
    await archiveButton!.trigger('click')
    await flushPromises()

    const reasonInput = wrapper.find('textarea')
    await reasonInput.setValue('会话已被用户删除，无法取证')
    const confirm = wrapper
      .findAll('button')
      .find((node) => node.text() === '确认归档')
    expect(confirm).toBeTruthy()
    await confirm!.trigger('click')
    await flushPromises()

    expect(supportApi.patchTicket).toHaveBeenCalledWith('ticket-1', {
      action: 'archive',
      close_reason: '会话已被用户删除，无法取证',
    })
  })
})

/** 找到「发送回复」按钮（Element Plus 会把文案包在 span 里）。 */
function sendButton(wrapper: Awaited<ReturnType<typeof mountView>>) {
  const button = wrapper.findAll('button').find((node) => node.text().includes('发送回复'))
  if (!button) throw new Error('没有找到发送回复按钮')
  return button
}

describe('SupportTicketDetailView（未接管只读）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    vi.mocked(supportApi.conversation).mockResolvedValue(transcript as never)
    vi.mocked(supportApi.patchTicket).mockResolvedValue({
      ticket_id: 'ticket-1',
      status: 'assigned',
      assigned_to_masked: '客服ab12cd',
      updated_at: '2026-03-01T09:20:00Z',
      request_id: 'req-1',
    } as never)
  })

  it('工单未接管时回复框与发送按钮均为禁用态，并说明原因', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(ticketFixture({ status: 'open' }))
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('未接管')
    expect(wrapper.text()).toContain('需先点击「接管」')
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    expect(sendButton(wrapper).attributes('disabled')).toBeDefined()
    // 会话仍可读：先看内容才能判断要不要接
    expect(wrapper.text()).toContain('回复用户')
  })

  it('未接管时即使绕过禁用态调用发送也不会发请求', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(ticketFixture({ status: 'open' }))
    const wrapper = await mountView()

    await wrapper.find('textarea').setValue('这条消息不应该发出去')
    // 直接调用组件内的发送逻辑（模拟脚本/竞态），后端边界之外再兜一层
    await (wrapper.vm as unknown as { sendReply: () => Promise<void> }).sendReply()
    await flushPromises()

    expect(supportApi.reply).not.toHaveBeenCalled()
  })

  it('已被其他客服接管时提示接管人姓名且保持禁用', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(
      ticketFixture({
        status: 'assigned',
        assigned_to_masked: '客服ab12cd',
        assigned_to_me: false,
      }),
    )
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('客服ab12cd')
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    expect(wrapper.text()).not.toContain('标记解决')
  })

  it('接管后回复框可用，可正常发送回复', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(
      ticketFixture({ status: 'assigned', assigned_to_masked: '客服ab12cd', assigned_to_me: true }),
    )
    vi.mocked(supportApi.reply).mockResolvedValue({
      message_id: 'message-9',
      conversation_id: 'conversation-1',
      created_at: '2026-03-01T09:21:00Z',
    } as never)
    const wrapper = await mountView()

    const textarea = wrapper.find('textarea')
    expect((textarea.element as HTMLTextAreaElement).disabled).toBe(false)
    await textarea.setValue('已受理，今天 18 点前回复。')
    await sendButton(wrapper).trigger('click')
    await flushPromises()

    expect(supportApi.reply).toHaveBeenCalledWith('ticket-1', { content: '已受理，今天 18 点前回复。' })
    expect(wrapper.text()).toContain('标记解决')
  })

  it('接管按钮只在未接管时出现，已由我接管后隐藏', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(ticketFixture({ status: 'open' }))
    const open = await mountView()
    expect(open.findAll('button').some((node) => node.text() === '接管')).toBe(true)
    expect(open.text()).not.toContain('已接管')

    vi.mocked(supportApi.ticket).mockResolvedValue(
      ticketFixture({ status: 'assigned', assigned_to_masked: '客服ab12cd', assigned_to_me: true }),
    )
    const owned = await mountView()
    expect(owned.findAll('button').some((node) => node.text() === '接管')).toBe(false)
    // 接管后要有明确的「已接管」状态，而不是按钮静默消失
    expect(owned.text()).toContain('已接管')
  })
})

/**
 * 回归：接管成功后界面仍是「未接管」、回复框仍然禁用。
 *
 * 现场原因：`assigned_to_me` 是后端派生字段，镜像未重建时返回体里没有它，前端拿到
 * `undefined` 就当成 false，于是自己刚接管的工单被误判为「别人接管的」——按钮不消失、
 * 回复永久禁用。后端 `assign` 未指定 assignee 时处理人就是调用者，所以「我这边成功」
 * 等价于「工单归我」，前端据此兜底。
 */
describe('SupportTicketDetailView（接管后状态同步）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    vi.mocked(supportApi.conversation).mockResolvedValue(transcript as never)
    vi.mocked(supportApi.patchTicket).mockResolvedValue({
      ticket_id: 'ticket-1',
      status: 'assigned',
      assigned_to_masked: '客服B01',
      updated_at: '2026-03-01T09:20:00Z',
      request_id: 'req-1',
    } as never)
  })

  it('后端不返回 assigned_to_me 时，接管成功也能立即解锁回复并显示「已接管」', async () => {
    const withoutField = (overrides: Partial<SupportTicketDetail> = {}): SupportTicketDetail => {
      const fixture = ticketFixture(overrides)
      delete fixture.assigned_to_me
      return fixture
    }
    vi.mocked(supportApi.ticket).mockResolvedValue(withoutField({ status: 'open' }))
    const wrapper = await mountView()
    expect((wrapper.find('textarea').element as HTMLTextAreaElement).disabled).toBe(true)

    // 接管成功后重新拉详情：旧后端依旧不返回 assigned_to_me
    vi.mocked(supportApi.ticket).mockResolvedValue(
      withoutField({ status: 'assigned', assigned_to_masked: '客服B01' }),
    )
    await (wrapper.vm as unknown as { runAction: (action: string) => Promise<void> }).runAction('assign')
    await flushPromises()

    expect((wrapper.find('textarea').element as HTMLTextAreaElement).disabled).toBe(false)
    await wrapper.find('textarea').setValue('已受理，稍后回复你。')
    expect(sendButton(wrapper).attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('已接管')
    expect(wrapper.findAll('button').some((node) => node.text() === '接管')).toBe(false)
    expect(wrapper.text()).toContain('标记解决')
  })

  it('后端返回 assigned_to_me=false 时以服务端为准，不误认领', async () => {
    const wrapper = await mountView()
    // 先让本机记下「我接管过」
    sessionStorage.setItem('shopmate.taken-over.v1.agent-1', JSON.stringify(['ticket-1']))
    vi.mocked(supportApi.ticket).mockResolvedValue(
      ticketFixture({ status: 'assigned', assigned_to_masked: '客服B01', assigned_to_me: false }),
    )
    await (wrapper.vm as unknown as { load: () => Promise<void> }).load()
    await flushPromises()

    expect((wrapper.find('textarea').element as HTMLTextAreaElement).disabled).toBe(true)
    // 权威值会顺手把本地记录清掉
    expect(sessionStorage.getItem('shopmate.taken-over.v1.agent-1')).toBeNull()
  })

  it('刷新会话能看到用户的新消息', async () => {
    vi.mocked(supportApi.ticket).mockResolvedValue(
      ticketFixture({ status: 'assigned', assigned_to_me: true }),
    )
    const wrapper = await mountView()

    vi.mocked(supportApi.conversation).mockResolvedValue({
      ...transcript,
      messages: [
        {
          message_id: 'message-2',
          role: 'user',
          content: '退款到哪了？',
          created_at: '2026-03-01T09:30:00Z',
          is_complete: true,
          citations: [],
        },
      ],
    } as never)

    const refresh = wrapper.findAll('button').find((node) => node.text().includes('刷新会话'))
    expect(refresh).toBeTruthy()
    await refresh!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('退款到哪了？')
  })

  it('进入详情页开启 10 秒会话轮询，离开时清理定时器', async () => {
    const setSpy = vi.spyOn(window, 'setInterval')
    const clearSpy = vi.spyOn(window, 'clearInterval')
    const wrapper = await mountView()

    expect(setSpy).toHaveBeenCalledWith(expect.any(Function), 10_000)
    wrapper.unmount()
    expect(clearSpy).toHaveBeenCalled()

    setSpy.mockRestore()
    clearSpy.mockRestore()
  })
})
