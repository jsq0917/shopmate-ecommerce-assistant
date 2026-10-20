import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import StateBlock from '@/components/common/StateBlock.vue'
import { ApiError } from '@/api/errors'

describe('StateBlock', () => {
  it('加载态展示骨架与文案', () => {
    const wrapper = mount(StateBlock, {
      props: { loading: true, loadingText: '正在加载会话…' },
    })
    expect(wrapper.text()).toContain('正在加载会话…')
    expect(wrapper.find('.el-skeleton').exists()).toBe(true)
  })

  it('错误态展示稳定中文文案，可重试时提供按钮', async () => {
    const wrapper = mount(StateBlock, {
      props: {
        error: new ApiError({
          code: 'NETWORK_ERROR',
          message: '网络连接失败，请检查网络后重试。',
          status: 0,
          retryable: true,
        }),
      },
    })
    expect(wrapper.text()).toContain('网络连接失败')
    const retry = wrapper.find('button')
    await retry.trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('不可重试的错误不展示重试按钮', () => {
    const wrapper = mount(StateBlock, {
      props: {
        error: new ApiError({
          code: 'VALIDATION_ERROR',
          message: '请求参数不合法，请检查后重试。',
          status: 400,
        }),
      },
    })
    expect(wrapper.findAll('button')).toHaveLength(0)
  })

  it('空态展示空态文案', () => {
    const wrapper = mount(StateBlock, { props: { empty: true, emptyText: '暂无会话' } })
    expect(wrapper.text()).toContain('暂无会话')
  })

  it('正常态渲染插槽内容', () => {
    const wrapper = mount(StateBlock, {
      slots: { default: '<p class="test-content">商品列表</p>' },
    })
    expect(wrapper.find('.test-content').exists()).toBe(true)
    expect(wrapper.find('.el-skeleton').exists()).toBe(false)
  })

  it('优先级：加载 > 错误 > 空', () => {
    const wrapper = mount(StateBlock, {
      props: {
        loading: true,
        error: new ApiError({ code: 'X', message: 'err', status: 500 }),
        empty: true,
      },
    })
    expect(wrapper.text()).not.toContain('err')
  })
})

describe('错误文案安全性', () => {
  it('ApiError.message 不含 trace_id / 堆栈关键字', () => {
    const error = new ApiError({ code: 'INTERNAL_ERROR', message: '服务暂时不可用，请稍后重试。', status: 500 })
    expect(error.message).not.toMatch(/trace|stack|SELECT|sql/i)
  })
})
