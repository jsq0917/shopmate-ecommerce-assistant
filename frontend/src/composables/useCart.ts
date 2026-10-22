/**
 * 本地购物车（仅存放用户主动选择 + 服务端返回的报价快照）。
 *
 * 价格与库存只是「加购那一刻」的展示快照；提交订单时后端会按 SKU 重新计价并校验库存，
 * 所以购物车里的数字不能当作结算依据（业务铁律 1）。
 */

import { computed, reactive, watch } from 'vue'

export interface CartItem {
  variantId: string
  productId: string
  title: string
  category: string
  priceCents: number
  currency: string
  quantity: number
  availableQty: number | null
}

interface CartState {
  items: CartItem[]
}

const STORAGE_KEY = 'shopmate.cart.v1'
const MAX_QUANTITY = 99

function load(): CartItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as CartState
    if (!Array.isArray(parsed.items)) return []
    return parsed.items
      .filter((item) => item && typeof item.variantId === 'string' && item.quantity > 0)
      .map((item) => ({ ...item, quantity: Math.min(item.quantity, MAX_QUANTITY) }))
  } catch {
    return []
  }
}

const state = reactive<CartState>({ items: load() })

watch(
  () => state.items,
  (items) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ items }))
    } catch {
      // 隐私模式或配额已满：购物车退化为内存态，不影响下单主流程。
    }
  },
  { deep: true },
)

export function useCart() {
  const items = computed(() => state.items)
  const count = computed(() => state.items.reduce((sum, item) => sum + item.quantity, 0))
  const subtotalCents = computed(() =>
    state.items.reduce((sum, item) => sum + item.priceCents * item.quantity, 0),
  )
  const isEmpty = computed(() => state.items.length === 0)

  function add(item: Omit<CartItem, 'quantity'>, quantity = 1): void {
    const limit = item.availableQty === null ? MAX_QUANTITY : Math.max(0, item.availableQty)
    if (limit <= 0) return
    const existing = state.items.find((row) => row.variantId === item.variantId)
    if (existing) {
      existing.quantity = Math.min(existing.quantity + quantity, limit, MAX_QUANTITY)
      return
    }
    state.items.push({
      ...item,
      quantity: Math.min(Math.max(1, quantity), limit, MAX_QUANTITY),
    })
  }

  function setQuantity(variantId: string, quantity: number): void {
    const row = state.items.find((item) => item.variantId === variantId)
    if (!row) return
    const limit = row.availableQty === null ? MAX_QUANTITY : Math.max(1, row.availableQty)
    row.quantity = Math.min(Math.max(1, Math.floor(quantity)), limit, MAX_QUANTITY)
  }

  function remove(variantId: string): void {
    const index = state.items.findIndex((item) => item.variantId === variantId)
    if (index >= 0) state.items.splice(index, 1)
  }

  function clear(): void {
    state.items.splice(0, state.items.length)
  }

  return { items, count, subtotalCents, isEmpty, add, setQuantity, remove, clear }
}

export { MAX_QUANTITY }
