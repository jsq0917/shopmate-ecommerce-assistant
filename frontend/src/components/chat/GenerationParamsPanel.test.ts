import { describe, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import GenerationParamsPanel from '@/components/chat/GenerationParamsPanel.vue'
import { generationDefaultsFixture } from '@/test/factories'

/**
 * Element Plus 的 ElSlider / ElInputNumber 在 jsdom 里依赖尺寸测量与内部 watcher，
 * 与 KnowledgeBaseSelect 测试里 ElSelect 的情况相同（库内部行为，与本组件无关）。
 * 这里用同形 stub 断言本组件的契约：控件绑定值、事件转发、默认值提示、生效值展示。
 */
const ElSliderStub = {
  name: 'ElSlider',
  props: ['modelValue', 'min', 'max', 'step', 'disabled', 'showInput'],
  emits: ['update:modelValue', 'change'],
  template: '<div class="el-slider-stub" />',
}

const ElInputNumberStub = {
  name: 'ElInputNumber',
  props: ['modelValue', 'min', 'max', 'step', 'disabled', 'size'],
  emits: ['update:modelValue', 'change'],
  template: '<div class="el-input-number-stub" />',
}

const ElButtonStub = {
  name: 'ElButton',
  props: ['disabled', 'type', 'size', 'text'],
  emits: ['click'],
  template: '<button class="el-button-stub" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
}

function mountPanel(props: Record<string, unknown> = {}) {
  return mount(GenerationParamsPanel, {
    props: {
      modelValue: {},
      defaults: generationDefaultsFixture(),
      ...props,
    },
    global: {
      stubs: { ElSlider: ElSliderStub, ElInputNumber: ElInputNumberStub, ElButton: ElButtonStub },
    },
  })
}

describe('GenerationParamsPanel', () => {
  it('未覆盖时展示服务端默认值作为生效值', () => {
    const wrapper = mountPanel()
    expect(wrapper.find('[data-testid="gen-effective"]').text()).toBe(
      '当前生效：温度 0.1 · top_p 默认（不限） · 最长输出 默认（不限） · 历史 10 轮',
    )
    expect(wrapper.find('[data-testid="gen-hint-temperature"]').text()).toBe('默认 0.1')
    expect(wrapper.find('[data-testid="gen-hint-history-turns"]').text()).toBe('默认 10 轮')
  })

  it('滑块停在与默认值等价的位置', () => {
    const wrapper = mountPanel()
    const temperature = wrapper.findComponent(ElSliderStub)
    expect(temperature.props('modelValue')).toBe(0.1)
    expect(temperature.props('min')).toBe(0)
    expect(temperature.props('max')).toBe(1)
  })

  it('max_tokens 输入框上限取服务端安全上限', () => {
    const wrapper = mountPanel({
      defaults: generationDefaultsFixture({ max_tokens_cap: 2048 }),
    })
    const maxTokens = wrapper.findAllComponents(ElInputNumberStub)[0]
    expect(maxTokens.props('max')).toBe(2048)
    expect(maxTokens.props('min')).toBe(256)
  })

  it('历史轮数上限为 10', () => {
    const wrapper = mountPanel()
    const history = wrapper.findAllComponents(ElInputNumberStub)[1]
    expect(history.props('max')).toBe(10)
    expect(history.props('min')).toBe(0)
  })

  it('拖动滑块实时向上发 update:modelValue，提交点才发 change', async () => {
    const wrapper = mountPanel()
    const temperature = wrapper.findComponent(ElSliderStub)

    temperature.vm.$emit('update:modelValue', 0.5)
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([{ temperature: 0.5 }])
    expect(wrapper.emitted('change')).toBeUndefined()

    temperature.vm.$emit('change', 0.5)
    await flushPromises()
    expect(wrapper.emitted('change')?.at(-1)).toEqual([{ temperature: 0.5 }])
  })

  it('数字输入提交时带上完整参数对象', async () => {
    const wrapper = mountPanel({ modelValue: { temperature: 0.7 } })
    const history = wrapper.findAllComponents(ElInputNumberStub)[1]

    history.vm.$emit('change', 4)
    await flushPromises()
    expect(wrapper.emitted('change')?.at(-1)).toEqual([{ temperature: 0.7, history_turns: 4 }])
  })

  it('已覆盖时提示「已设置」并展示生效值', () => {
    const wrapper = mountPanel({
      modelValue: { temperature: 0.7, top_p: 0.9, max_tokens: 512, history_turns: 0 },
    })
    expect(wrapper.find('[data-testid="gen-hint-temperature"]').text()).toBe('已设置')
    expect(wrapper.find('[data-testid="gen-effective"]').text()).toBe(
      '当前生效：温度 0.7 · top_p 0.9 · 最长输出 512 tokens · 历史 0 轮',
    )
    const temperature = wrapper.findComponent(ElSliderStub)
    expect(temperature.props('modelValue')).toBe(0.7)
  })

  it('「恢复默认」把所有字段显式置空后发出', async () => {
    const wrapper = mountPanel({ modelValue: { temperature: 0.7, history_turns: 4 } })
    const reset = wrapper.find('[data-testid="gen-reset"]')

    await reset.trigger('click')
    expect(wrapper.emitted('change')?.at(-1)).toEqual([
      { temperature: null, top_p: null, max_tokens: null, history_turns: null },
    ])
  })

  it('没有任何覆盖时禁用「恢复默认」', () => {
    const wrapper = mountPanel()
    const reset = wrapper.findComponent(ElButtonStub)
    expect(reset.props('disabled')).toBe(true)
  })

  it('默认值缺失（加载中/失败）时禁用全部控件', () => {
    const wrapper = mountPanel({ defaults: null })
    expect(wrapper.findComponent(ElSliderStub).props('disabled')).toBe(true)
    expect(wrapper.findAllComponents(ElInputNumberStub)[0].props('disabled')).toBe(true)
    expect(wrapper.find('[data-testid="gen-effective"]').text()).toContain('暂不可用')
  })

  it('保存进行中禁用控件，避免并发修改', () => {
    const wrapper = mountPanel({ loading: true })
    expect(wrapper.findComponent(ElSliderStub).props('disabled')).toBe(true)
  })

  it('父级传入 disabled（如流式进行中）时禁用控件', () => {
    const wrapper = mountPanel({ disabled: true })
    expect(wrapper.findComponent(ElSliderStub).props('disabled')).toBe(true)
  })
})
