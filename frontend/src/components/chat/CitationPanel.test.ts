import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import CitationPanel from '@/components/chat/CitationPanel.vue'
import { citationFixture } from '@/test/factories'

describe('CitationPanel', () => {
  it('展示文档、章节、页码、版本、生效期与片段', () => {
    const wrapper = mount(CitationPanel, { props: { citations: [citationFixture()] } })
    expect(wrapper.text()).toContain('退换货政策')
    expect(wrapper.text()).toContain('章节：第七条 退货期限')
    expect(wrapper.text()).toContain('第 3 页')
    expect(wrapper.text()).toContain('版本 v3')
    expect(wrapper.text()).toContain('2026-01-01 起长期有效')
    expect(wrapper.text()).toContain('签收后 7 天内可申请退货。')
    expect(wrapper.text()).toContain('检索时间')
  })

  it('有生效结束时间时展示区间', () => {
    const wrapper = mount(CitationPanel, {
      props: {
        citations: [
          citationFixture({
            effective_from: '2026-01-01T00:00:00Z',
            effective_to: '2026-12-31T00:00:00Z',
          }),
        ],
      },
    })
    expect(wrapper.text()).toContain('2026-01-01 至 2026-12-31')
    expect(wrapper.text()).not.toContain('长期有效')
  })

  it('生效期缺失时明确标注未知', () => {
    const wrapper = mount(CitationPanel, {
      props: {
        citations: [citationFixture({ effective_from: null, effective_to: null })],
      },
    })
    expect(wrapper.text()).toContain('生效期未知')
  })

  it('无引用时展示空态文案', () => {
    const wrapper = mount(CitationPanel, { props: { citations: [] } })
    expect(wrapper.text()).toContain('本轮回答没有可展示的引用')
  })

  it('多条引用按序渲染', () => {
    const wrapper = mount(CitationPanel, {
      props: {
        citations: [citationFixture(), citationFixture({ citation_id: 'cit-2', title: '配送政策' })],
      },
    })
    expect(wrapper.findAll('.sm-citation')).toHaveLength(2)
    expect(wrapper.text()).toContain('配送政策')
  })
})
