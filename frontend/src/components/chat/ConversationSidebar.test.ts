import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ElMessageBox, type MessageBoxData } from 'element-plus'

import ConversationSidebar from '@/components/chat/ConversationSidebar.vue'
import { conversationFixture } from '@/test/factories'

// 只替换 ElMessageBox，其余 Element Plus 组件保持真实实现。
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return { ...actual, ElMessageBox: { confirm: vi.fn() } }
})

const conversations = [
  conversationFixture(),
  conversationFixture({ id: '22222222-2222-4222-8222-222222222222', title: '订单查询' }),
]

function mountSidebar(activeId: string | null = null) {
  return mount(ConversationSidebar, {
    props: { conversations, activeId, loading: false },
  })
}

describe('ConversationSidebar', () => {
  beforeEach(() => {
    vi.mocked(ElMessageBox.confirm).mockReset()
  })

  it('渲染会话列表', () => {
    const wrapper = mountSidebar()
    expect(wrapper.text()).toContain('耳机咨询')
    expect(wrapper.text()).toContain('订单查询')
  })

  it('点击会话触发 select', async () => {
    const wrapper = mountSidebar()
    await wrapper.findAll('.sm-conversation-select')[1].trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toBe('22222222-2222-4222-8222-222222222222')
  })

  it('activeId 高亮当前会话', () => {
    const wrapper = mountSidebar('11111111-1111-4111-8111-111111111111')
    expect(wrapper.findAll('.sm-conversation-item')[0].classes()).toContain('sm-conversation-active')
  })

  it('内联重命名：回车提交', async () => {
    const wrapper = mountSidebar()
    await wrapper.find('button[aria-label="重命名会话"]').trigger('click')

    const input = wrapper.find('input')
    await input.setValue('新标题')
    await input.trigger('keyup.enter')

    expect(wrapper.emitted('rename')?.[0]).toEqual([
      '11111111-1111-4111-8111-111111111111',
      '新标题',
    ])
  })

  it('重命名空标题不提交', async () => {
    const wrapper = mountSidebar()
    await wrapper.find('button[aria-label="重命名会话"]').trigger('click')
    const input = wrapper.find('input')
    await input.setValue('   ')
    await input.trigger('keyup.enter')
    expect(wrapper.emitted('rename')).toBeUndefined()
  })

  it('删除需二次确认，确认后触发 remove', async () => {
    vi.mocked(ElMessageBox.confirm).mockResolvedValue({ action: 'confirm' } as MessageBoxData)
    const wrapper = mountSidebar()
    await wrapper.find('button[aria-label="删除会话"]').trigger('click')

    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
    await vi.waitFor(() => {
      expect(wrapper.emitted('remove')?.[0]?.[0]).toBe('11111111-1111-4111-8111-111111111111')
    })
  })

  it('取消删除不触发 remove', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const wrapper = mountSidebar()
    await wrapper.find('button[aria-label="删除会话"]').trigger('click')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(wrapper.emitted('remove')).toBeUndefined()
  })

  it('空列表展示空态', () => {
    const wrapper = mount(ConversationSidebar, {
      props: { conversations: [], activeId: null, loading: false },
    })
    expect(wrapper.text()).toContain('暂无会话')
  })
})
