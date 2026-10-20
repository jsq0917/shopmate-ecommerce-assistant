import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import ReturnWizard from '@/components/orders/ReturnWizard.vue'
import { ApiError } from '@/api/errors'
import type { CreateReturnData, OrderItemSummary, ReturnEligibilityData } from '@/api/types'

vi.mock('@/api/endpoints', () => ({
  returnsApi: { eligibility: vi.fn(), create: vi.fn() },
}))

const { returnsApi } = await import('@/api/endpoints')

const items: OrderItemSummary[] = [
  {
    id: 'item-1',
    sku: 'SKU-1',
    title: 'SoundCore Q35 降噪耳机',
    quantity: 1,
    unit_price_cents: 29900,
    status: 'delivered',
  },
]

function eligibilityFixture(overrides: Partial<ReturnEligibilityData> = {}): ReturnEligibilityData {
  return {
    decision: 'eligible',
    decision_code: 'RETURN_WINDOW_OK',
    error_code: null,
    eligible: true,
    needs_clarification: false,
    needs_manual_review: false,
    can_create_return_request: true,
    handoff_required: false,
    matched_rule_codes: ['WITHIN_7_DAYS'],
    deadline_at: '2026-03-08T00:00:00Z',
    required_materials: ['商品原包装'],
    next_action: '提交退货申请',
    eligibility_token: 'tok-1',
    eligibility_expires_at: '2026-03-01T10:00:00Z',
    rule_version: 'return-rules@v3',
    evaluated_at: '2026-03-01T09:30:00Z',
    ...overrides,
  }
}

function createdFixture(): CreateReturnData {
  return {
    return_request_id: 'rr-1',
    status: 'submitted',
    submitted_at: '2026-03-01T09:35:00Z',
    review_required: true,
    required_materials: ['商品原包装'],
    next_action: '等待审核',
    refund_status: 'not_created',
    notice: '提交仅生成退货申请，退款需审核后另行处理。',
    idempotent_replay: false,
  }
}

async function mountWizard() {
  const wrapper = mount(ReturnWizard, { props: { orderId: 'order-1', items } })
  await flushPromises()
  return wrapper
}

/** 选择订单商品（ElSelect v-model）。 */
async function selectItem(wrapper: Awaited<ReturnType<typeof mountWizard>>) {
  const select = wrapper.findComponent({ name: 'ElSelect' })
  await select.vm.$emit('update:modelValue', 'item-1')
}

describe('ReturnWizard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染表单与免责提示', async () => {
    const wrapper = await mountWizard()
    expect(wrapper.text()).toContain('申请退货')
    expect(wrapper.text()).toContain('提交申请不代表退款成功')
    expect(wrapper.text()).toContain('选择要退货的商品')
    expect(wrapper.text()).toContain('检查退货资格')
    // 未选择商品时不可检查
    const checkButton = wrapper.findAll('button').find((btn) => btn.text().includes('检查退货资格'))
    expect(checkButton!.attributes('disabled')).toBeDefined()
  })

  it('资格检查通过：展示决策、规则版本与截止时间', async () => {
    vi.mocked(returnsApi.eligibility).mockResolvedValue(eligibilityFixture())
    const wrapper = await mountWizard()
    await selectItem(wrapper)

    const checkButton = wrapper.findAll('button').find((btn) => btn.text().includes('检查退货资格'))
    await checkButton!.trigger('click')
    await flushPromises()

    expect(returnsApi.eligibility).toHaveBeenCalledWith({
      order_id: 'order-1',
      order_item_id: 'item-1',
      reason_code: 'SIZE_OR_FIT',
    })
    expect(wrapper.text()).toContain('符合退货条件')
    expect(wrapper.text()).toContain('return-rules@v3')
    expect(wrapper.text()).toContain('WITHIN_7_DAYS')
    expect(wrapper.text()).toContain('商品原包装')
    // 未勾选确认前不可提交
    const submitButton = wrapper.findAll('button').find((btn) => btn.text().includes('提交退货申请'))
    expect(submitButton!.attributes('disabled')).toBeDefined()
  })

  it('需人工审核时提示转人工，不展示提交入口', async () => {
    vi.mocked(returnsApi.eligibility).mockResolvedValue(
      eligibilityFixture({
        decision: 'needs_manual_review',
        decision_code: 'HIGH_VALUE_MANUAL',
        eligible: false,
        can_create_return_request: false,
        needs_manual_review: true,
        eligibility_token: null,
      }),
    )
    const wrapper = await mountWizard()
    await selectItem(wrapper)
    const checkButton = wrapper.findAll('button').find((btn) => btn.text().includes('检查退货资格'))
    await checkButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('需要人工审核')
    expect(wrapper.text()).toContain('转人工')
    // 不可创建申请时不展示提交按钮
    const submitButton = wrapper.findAll('button').find((btn) => btn.text().includes('提交退货申请'))
    expect(submitButton).toBeUndefined()
  })

  it('资格检查失败展示错误', async () => {
    vi.mocked(returnsApi.eligibility).mockRejectedValue(
      new ApiError({ code: 'ORDER_NOT_FOUND', message: '未找到可由当前账号访问的订单。', status: 404 }),
    )
    const wrapper = await mountWizard()
    await selectItem(wrapper)
    const checkButton = wrapper.findAll('button').find((btn) => btn.text().includes('检查退货资格'))
    await checkButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('未找到可由当前账号访问的订单')
  })

  it('勾选确认后提交：展示 submitted 与 not_created，并发出 created 事件', async () => {
    vi.mocked(returnsApi.eligibility).mockResolvedValue(eligibilityFixture())
    vi.mocked(returnsApi.create).mockResolvedValue(createdFixture())

    const wrapper = await mountWizard()
    await selectItem(wrapper)
    const checkButton = wrapper.findAll('button').find((btn) => btn.text().includes('检查退货资格'))
    await checkButton!.trigger('click')
    await flushPromises()

    // 勾选确认（明确知晓提交≠退款）
    const checkbox = wrapper.findComponent({ name: 'ElCheckbox' })
    await checkbox.vm.$emit('update:modelValue', true)

    const submitButton = wrapper.findAll('button').find((btn) => btn.text().includes('提交退货申请'))
    expect(submitButton!.attributes('disabled')).toBeUndefined()
    await submitButton!.trigger('click')
    await flushPromises()

    expect(returnsApi.create).toHaveBeenCalledTimes(1)
    const [body, idempotencyKey] = vi.mocked(returnsApi.create).mock.calls[0]
    expect(body).toMatchObject({
      order_id: 'order-1',
      order_item_id: 'item-1',
      reason_code: 'SIZE_OR_FIT',
      eligibility_token: 'tok-1',
      confirmed: true,
    })
    expect(idempotencyKey).toBeTruthy()

    expect(wrapper.text()).toContain('退货申请已提交')
    expect(wrapper.text()).toContain('submitted')
    expect(wrapper.text()).toContain('not_created')
    expect(wrapper.text()).toContain('提交仅生成退货申请，退款需审核后另行处理。')
    expect(wrapper.emitted('created')).toHaveLength(1)
  })

  it('提交失败展示错误且不显示成功态', async () => {
    vi.mocked(returnsApi.eligibility).mockResolvedValue(eligibilityFixture())
    vi.mocked(returnsApi.create).mockRejectedValue(
      new ApiError({ code: 'DUPLICATE_RETURN', message: '已存在有效的退货申请，请勿重复提交。', status: 409 }),
    )
    const wrapper = await mountWizard()
    await selectItem(wrapper)
    const checkButton = wrapper.findAll('button').find((btn) => btn.text().includes('检查退货资格'))
    await checkButton!.trigger('click')
    await flushPromises()

    const checkbox = wrapper.findComponent({ name: 'ElCheckbox' })
    await checkbox.vm.$emit('update:modelValue', true)
    const submitButton = wrapper.findAll('button').find((btn) => btn.text().includes('提交退货申请'))
    await submitButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('已存在有效的退货申请，请勿重复提交。')
    expect(wrapper.text()).not.toContain('退货申请已提交')
  })
})
