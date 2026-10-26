import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import ProductsView from '@/views/ProductsView.vue'
import { productCardFixture } from '@/test/factories'
import type { ProductCardItem, ProductSearchData } from '@/api/types'

vi.mock('@/api/endpoints', () => ({
  productsApi: {
    featured: vi.fn(),
    search: vi.fn(),
    detail: vi.fn(),
    compare: vi.fn(),
  },
}))

const { productsApi } = await import('@/api/endpoints')

function searchResponse(count = 2): ProductSearchData {
  const items: ProductCardItem[] = Array.from({ length: count }, (_, index) => ({
    ...productCardFixture({
      product_id: `p-${index}`,
      title: `降噪耳机 ${index + 1}`,
      price_cents: 19900 + index * 100,
      as_of: '2026-10-24T12:00:00Z',
    }),
    brand: 'SoundMate',
    category: '数码配件',
    sku: `SM-NC-${index + 1}`,
    as_of: '2026-10-24T12:00:00Z',
  }))
  return {
    items,
    as_of: '2026-10-24T12:00:00Z',
    is_synthetic: true,
    next_cursor: null,
  }
}

async function mountProducts() {
  const wrapper = mount(ProductsView)
  await flushPromises()
  return wrapper
}

describe('ProductsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(productsApi.featured).mockResolvedValue(searchResponse(24))
    vi.mocked(productsApi.search).mockResolvedValue(searchResponse(2))
  })

  it('首页精选使用 featured 端点允许的上限（le=24）', async () => {
    await mountProducts()
    expect(productsApi.featured).toHaveBeenCalledWith({ limit: 24 })
  })

  it('点击快捷标签发起搜索，limit 不超过 search 端点契约上限（le=20）', async () => {
    const wrapper = await mountProducts()
    vi.mocked(productsApi.search).mockClear()

    const tag = wrapper.findAll('.sm-hero-tag').find((b) => b.text() === '降噪耳机')
    expect(tag).toBeTruthy()
    await tag!.trigger('click')
    await flushPromises()

    expect(productsApi.search).toHaveBeenCalledTimes(1)
    const params = vi.mocked(productsApi.search).mock.calls[0]?.[0]
    expect(params?.q).toBe('降噪耳机')
    expect(params?.limit).toBeLessThanOrEqual(20)
    // 搜索结果渲染到卡片列表，而不是停在错误态。
    expect(wrapper.text()).toContain('降噪耳机 1')
    expect(wrapper.find('.el-alert--error').exists()).toBe(false)
  })

  it('输入框关键词搜索同样遵守 limit 契约', async () => {
    const wrapper = await mountProducts()
    vi.mocked(productsApi.search).mockClear()

    const input = wrapper.find('input')
    await input.setValue('机械键盘')
    await wrapper.find('button').trigger('click')
    await flushPromises()

    const params = vi.mocked(productsApi.search).mock.calls[0]?.[0]
    expect(params?.q).toBe('机械键盘')
    expect(params?.limit).toBeLessThanOrEqual(20)
  })
})
