import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import SupportTicketDetailView from '@/views/SupportTicketDetailView.vue'
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
  const wrapper = mount(SupportTicketDetailView)
  await flushPromises()
  return wrapper
}

describe('SupportTicketDetailView（工单详情）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
