import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import KnowledgeBaseSelect from '@/components/chat/KnowledgeBaseSelect.vue'
import { KB_CN, KB_SG, knowledgeBaseFixture } from '@/test/factories'

const OPTIONS = [
  knowledgeBaseFixture({ id: KB_CN, name: 'policy-cn' }),
  knowledgeBaseFixture({ id: KB_SG, name: 'policy-sg', region: 'SG' }),
]

/**
 * Element Plus 的 ElSelect 在 jsdom 里会因 teleport 下拉与内部 watcher 相互触发而报
 * "Maximum recursive updates"（库内部行为，与本组件无关）。这里用同形 stub 断言本组件
 * 的契约（透传 / 提示文案 / 事件转发），Element Plus 自身行为不在本测试范围。
 */
const ElSelectStub = {
  name: 'ElSelect',
  props: ['modelValue', 'disabled', 'loading', 'multiple', 'placeholder', 'collapseTags'],
  emits: ['update:modelValue', 'change'],
  template: '<div class="el-select-stub"><slot /></div>',
}

const ElOptionStub = {
  name: 'ElOption',
  props: ['label', 'value'],
  template: '<div class="el-option-stub">{{ label }}</div>',
}

function mountSelect(props: Record<string, unknown> = {}) {
  return mount(KnowledgeBaseSelect, {
    props: { options: OPTIONS, modelValue: [], ...props },
    global: { stubs: { ElSelect: ElSelectStub, ElOption: ElOptionStub } },
  })
}

describe('KnowledgeBaseSelect', () => {
  it('空选时提示「将检索全部可见知识库」', () => {
    const wrapper = mountSelect()
    expect(wrapper.find('[data-testid="kb-hint"]').text()).toContain('全部可见知识库')
    expect(wrapper.find('[data-testid="kb-hint-selected"]').exists()).toBe(false)
  })

  it('选中多个后提示只检索所选', () => {
    const wrapper = mountSelect({ modelValue: [KB_CN, KB_SG] })
    expect(wrapper.find('[data-testid="kb-hint-selected"]').text()).toContain('2 个知识库')
    expect(wrapper.find('[data-testid="kb-hint"]').exists()).toBe(false)
  })

  it('多选，并把选择转发给父级', async () => {
    const wrapper = mountSelect()
    const select = wrapper.findComponent(ElSelectStub)
    // 模板里是裸属性，作为 prop 透传给 ElSelect（值为空字符串），存在即表示多选。
    expect(Object.keys(select.props())).toContain('multiple')

    select.vm.$emit('update:modelValue', [KB_SG])
    select.vm.$emit('change', [KB_SG])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[KB_SG]])
    expect(wrapper.emitted('change')?.at(-1)).toEqual([[KB_SG]])
  })

  it('没有任何知识库时禁用并给出说明', () => {
    const wrapper = mountSelect({ options: [] })
    const select = wrapper.findComponent(ElSelectStub)
    expect(select.props('disabled')).toBe(true)
    expect(select.props('placeholder')).toContain('暂无知识库')
  })

  it('请求进行中禁用且显示 loading，避免并发改选择', () => {
    const wrapper = mountSelect({ loading: true })
    const select = wrapper.findComponent(ElSelectStub)
    expect(select.props('loading')).toBe(true)
    expect(select.props('disabled')).toBe(true)
  })

  it('选项按传入顺序渲染', () => {
    const wrapper = mountSelect()
    const labels = wrapper.findAllComponents(ElOptionStub).map((item) => item.props('label'))
    expect(labels).toEqual(['policy-cn', 'policy-sg'])
  })
})
