import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import ProductCardList from '@/components/chat/ProductCardList.vue'
import { productCardFixture } from '@/test/factories'

describe('ProductCardList', () => {
  const cards = [
    productCardFixture(),
    productCardFixture({
      product_id: 'prod-2',
      variant_id: 'var-2',
      title: 'Anker 声阔 Q30',
      price_cents: 79900,
      stock_status: 'out_of_stock',
      available_qty: null,
      is_synthetic: true,
      as_of: null,
    }),
  ]

  it('渲染价格、库存与数据时间，不虚构数值', () => {
    const wrapper = mount(ProductCardList, { props: { cards } })
    expect(wrapper.text()).toContain('¥299.00')
    expect(wrapper.text()).toContain('有货')
    expect(wrapper.text()).toContain('缺货')
    expect(wrapper.text()).toContain('数量未知')
    expect(wrapper.text()).toContain('合成')
  })

  it('库存未知时不展示可售数量', () => {
    const wrapper = mount(ProductCardList, {
      props: {
        cards: [productCardFixture({ stock_status: 'unknown', available_qty: null })],
      },
    })
    expect(wrapper.text()).toContain('库存未知')
    expect(wrapper.text()).not.toContain('可售')
  })

  it('selectable 模式勾选触发 toggle-compare', async () => {
    const wrapper = mount(ProductCardList, {
      props: { cards, selectable: true, selectedIds: ['prod-1'] },
    })
    // 第一张卡片的勾选框（findComponent 返回首个匹配）
    const checkbox = wrapper.findComponent({ name: 'ElCheckbox' })
    await checkbox.vm.$emit('change', true)
    expect(wrapper.emitted('toggle-compare')?.[0]?.[0]).toBe('prod-1')
  })

  it('详情按钮触发 detail 事件', async () => {
    const wrapper = mount(ProductCardList, { props: { cards } })
    const detailButton = wrapper
      .findAll('button')
      .find((btn) => btn.text().includes('详情'))
    await detailButton!.trigger('click')
    const emitted = wrapper.emitted('detail')
    expect(emitted).toHaveLength(1)
    expect((emitted?.[0]?.[0] as { product_id: string }).product_id).toBe('prod-1')
  })

  it('空属性不渲染 chip', () => {
    const wrapper = mount(ProductCardList, {
      props: { cards: [productCardFixture({ attributes: {} })] },
    })
    expect(wrapper.findAll('.sm-attr-chip')).toHaveLength(0)
  })
})
