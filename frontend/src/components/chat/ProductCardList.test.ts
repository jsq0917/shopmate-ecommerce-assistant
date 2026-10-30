import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'

import ProductCardList from '@/components/chat/ProductCardList.vue'
import { useCart } from '@/composables/useCart'
import { productsApi } from '@/api/endpoints'
import type { ProductDetailData, VariantDetailItem } from '@/api/types'
import { productCardFixture } from '@/test/factories'

// 加购复核走 GET /products/{id}：这里只关心「前端拿到复核结果后怎么处理」，
// 所以把商品详情接口整体替换成可控的 mock，不触网。
vi.mock('@/api/endpoints', () => ({
  productsApi: { detail: vi.fn() },
}))

const detailMock = vi.mocked(productsApi.detail)

function detailFixture(variant: Partial<VariantDetailItem> = {}): ProductDetailData {
  return {
    product: {
      id: 'prod-1',
      title: '声阔 SL-NC300 入耳式降噪耳机',
      description: null,
      brand: '声阔',
      category: '耳机',
      attributes: {},
      status: 'active',
      is_synthetic: true,
      image_url: null,
      stock_summary: {},
      variants: [
        {
          id: 'var-1',
          sku: 'SKU-1',
          title: '声阔 SL-NC300 入耳式降噪耳机',
          attributes: {},
          price_cents: 29900,
          currency: 'CNY',
          status: 'active',
          available_qty: 12,
          stock_status: 'in_stock',
          stock_updated_at: '2026-10-27T11:59:00Z',
          ...variant,
        },
      ],
    },
    as_of: '2026-10-27T11:59:00Z',
  }
}

/** 每张卡片的页脚按钮固定是 [可选「比较」][详情][加购]，所以取卡片内最后一个按钮。 */
function addButton(wrapper: VueWrapper, index = 0): ReturnType<VueWrapper['find']> {
  const article = wrapper.findAll('article').at(index)
  if (!article) throw new Error('没有找到商品卡片')
  const button = article.findAll('button').at(-1)
  if (!button) throw new Error('没有找到加购按钮')
  return button
}

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

  beforeEach(() => {
    useCart().clear()
    detailMock.mockReset()
    document.body.innerHTML = ''
  })

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

  it('未显式传 buyable 时加购按钮仍可点击（回归：布尔 prop 缺省被转成 false）', () => {
    const wrapper = mount(ProductCardList, { props: { cards: [productCardFixture()] } })
    expect(addButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('buyable=false 或缺货时按钮禁用', () => {
    const notBuyable = mount(ProductCardList, {
      props: { cards: [productCardFixture()], buyable: false },
    })
    expect(addButton(notBuyable).attributes('disabled')).toBeDefined()

    const soldOut = mount(ProductCardList, {
      props: { cards: [productCardFixture({ stock_status: 'out_of_stock', available_qty: null })] },
    })
    expect(addButton(soldOut).attributes('disabled')).toBeDefined()
  })

  it('点击加购复核库存后写入购物车，并用复核结果刷新快照', async () => {
    detailMock.mockResolvedValue(detailFixture({ price_cents: 25900, available_qty: 5 }))
    const wrapper = mount(ProductCardList, { props: { cards: [productCardFixture()], revalidate: true } })

    await addButton(wrapper).trigger('click')
    await flushPromises()

    const cart = useCart()
    expect(detailMock).toHaveBeenCalledWith('prod-1')
    expect(cart.count.value).toBe(1)
    expect(cart.items.value[0]).toMatchObject({
      variantId: 'var-1',
      productId: 'prod-1',
      priceCents: 25900,
      availableQty: 5,
      quantity: 1,
    })
    expect(addButton(wrapper).text()).toContain('已加入')
  })

  it('复核到售罄时不写入购物车', async () => {
    detailMock.mockResolvedValue(
      detailFixture({ stock_status: 'out_of_stock', available_qty: 0 }),
    )
    const wrapper = mount(ProductCardList, { props: { cards: [productCardFixture()], revalidate: true } })

    await addButton(wrapper).trigger('click')
    await flushPromises()

    expect(useCart().count.value).toBe(0)
    expect(document.body.textContent).toContain('售罄')
    expect(addButton(wrapper).text()).toContain('加购')
  })

  it('重复点击只在途一次，不会重复加购', async () => {
    let resolveDetail: (value: ProductDetailData) => void = () => {}
    detailMock.mockImplementation(
      () =>
        new Promise<ProductDetailData>((resolve) => {
          resolveDetail = resolve
        }),
    )
    const wrapper = mount(ProductCardList, { props: { cards: [productCardFixture()], revalidate: true } })

    const button = addButton(wrapper)
    await button.trigger('click')
    await button.trigger('click')
    await button.trigger('click')

    expect(detailMock).toHaveBeenCalledTimes(1)
    expect(button.text()).toContain('加购中')

    resolveDetail(detailFixture())
    await flushPromises()
    expect(useCart().count.value).toBe(1)
  })

  it('复核接口失败时退回卡片快照加入，不阻断加购', async () => {
    detailMock.mockRejectedValue(new Error('network down'))
    const wrapper = mount(ProductCardList, { props: { cards: [productCardFixture()], revalidate: true } })

    await addButton(wrapper).trigger('click')
    await flushPromises()

    const cart = useCart()
    expect(cart.count.value).toBe(1)
    expect(cart.items.value[0].priceCents).toBe(29900)
    expect(document.body.textContent).toContain('库存校验失败')
  })

  it('已达可售上限时数量不再增加', async () => {
    detailMock.mockResolvedValue(detailFixture({ available_qty: 1 }))
    const wrapper = mount(ProductCardList, {
      props: { cards: [productCardFixture({ available_qty: 1 })], revalidate: true },
    })

    await addButton(wrapper).trigger('click')
    await flushPromises()
    await addButton(wrapper).trigger('click')
    await flushPromises()

    expect(useCart().count.value).toBe(1)
    expect(document.body.textContent).toContain('最多可买 1 件')
  })

  it('未开启复核时不调用商品详情接口（商品中心列表无需二次查询）', async () => {
    const wrapper = mount(ProductCardList, { props: { cards: [productCardFixture()] } })

    await addButton(wrapper).trigger('click')
    await flushPromises()

    expect(detailMock).not.toHaveBeenCalled()
    expect(useCart().count.value).toBe(1)
  })
})
