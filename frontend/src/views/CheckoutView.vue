<script setup lang="ts">
/**
 * 结算页：核对购物车 → 提交订单 → 可选立即支付（模拟）。
 *
 * 页面上的价格只是加购时的快照；提交后以后端返回的订单金额为准，并在成功提示里
 * 展示服务端算出的实付金额。
 */

import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElAlert, ElButton, ElInput, ElMessage } from 'element-plus'

import ProductThumb from '@/components/common/ProductThumb.vue'
import { ordersApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import { useCart } from '@/composables/useCart'
import { formatMoney } from '@/utils/format'

const router = useRouter()
const cart = useCart()

const address = ref('上海市 浦东新区 示例路 ** 号（合成地址）')
const submitting = ref(false)
const error = ref<ApiError | null>(null)

const items = computed(() => cart.items.value)
const totalCents = computed(() => cart.subtotalCents.value)
const totalCount = computed(() => cart.count.value)

async function submit(payNow: boolean): Promise<void> {
  if (cart.isEmpty.value || submitting.value) return
  submitting.value = true
  error.value = null
  try {
    const order = await ordersApi.create({
      items: items.value.map((item) => ({ variant_id: item.variantId, quantity: item.quantity })),
      shipping_address_masked: address.value.trim() || null,
    })
    if (payNow) {
      await ordersApi.pay(order.id)
      ElMessage.success(`订单 ${order.order_no} 已支付`)
    } else {
      ElMessage.success(`订单 ${order.order_no} 已创建，请尽快完成支付`)
    }
    cart.clear()
    await router.push({ name: 'order-detail', params: { orderId: order.id } })
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="sm-page">
    <div class="sm-page-header">
      <div>
        <h2 class="sm-page-title">确认订单</h2>
        <p class="sm-page-subtitle">价格与库存会在提交时由服务端重新校验，页面金额仅供参考。</p>
      </div>
      <ElButton @click="router.push('/products')">继续购物</ElButton>
    </div>

    <ElAlert
      v-if="error"
      type="error"
      :closable="false"
      show-icon
      :title="error.message"
      class="sm-block"
    />

    <div v-if="cart.isEmpty.value" class="sm-card sm-empty">
      <p>购物车还是空的。</p>
      <ElButton type="primary" @click="router.push('/products')">去挑商品</ElButton>
    </div>

    <div v-else class="sm-checkout">
      <section class="sm-card sm-lines">
        <h3 class="sm-section-title">商品清单（{{ totalCount }} 件）</h3>
        <article v-for="item in items" :key="item.variantId" class="sm-line">
          <ProductThumb :category="item.category" :title="item.title" size="sm" />
          <div class="sm-line-main">
            <p class="sm-line-title">{{ item.title }}</p>
            <p class="sm-muted">单价 {{ formatMoney(item.priceCents, item.currency) }}</p>
          </div>
          <div class="sm-line-qty">
            <ElButton
              size="small"
              :disabled="item.quantity <= 1"
              @click="cart.setQuantity(item.variantId, item.quantity - 1)"
            >
              −
            </ElButton>
            <span class="sm-qty">{{ item.quantity }}</span>
            <ElButton size="small" @click="cart.setQuantity(item.variantId, item.quantity + 1)">
              +
            </ElButton>
          </div>
          <div class="sm-line-total sm-price">
            {{ formatMoney(item.priceCents * item.quantity, item.currency) }}
          </div>
          <ElButton size="small" text type="danger" @click="cart.remove(item.variantId)">移除</ElButton>
        </article>
      </section>

      <aside class="sm-card sm-summary">
        <h3 class="sm-section-title">收货与支付</h3>
        <label class="sm-field">
          <span class="sm-muted">收货地址（演示用脱敏地址）</span>
          <ElInput v-model="address" maxlength="120" show-word-limit />
        </label>
        <div class="sm-summary-row">
          <span>商品金额</span>
          <span>{{ formatMoney(totalCents, 'CNY') }}</span>
        </div>
        <div class="sm-summary-row">
          <span>运费</span>
          <span class="sm-muted">包邮</span>
        </div>
        <hr class="sm-divider" />
        <div class="sm-summary-total">
          <span>应付</span>
          <strong class="sm-price">{{ formatMoney(totalCents, 'CNY') }}</strong>
        </div>
        <ElButton
          type="primary"
          size="large"
          class="sm-submit"
          :loading="submitting"
          @click="submit(true)"
        >
          提交并支付
        </ElButton>
        <ElButton class="sm-submit" :loading="submitting" @click="submit(false)">
          仅提交订单
        </ElButton>
        <p class="sm-muted">支付为模拟流程，不接入真实资金；支付后可在订单详情申请退款。</p>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.sm-block {
  margin-bottom: 14px;
}

.sm-checkout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  align-items: start;
}

.sm-lines {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sm-line {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid var(--sm-border);
}

.sm-line:last-child {
  border-bottom: none;
}

.sm-line-main {
  flex: 1;
  min-width: 0;
}

.sm-line-title {
  margin: 0;
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sm-line-qty {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sm-qty {
  min-width: 26px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.sm-line-total {
  min-width: 72px;
  text-align: right;
}

.sm-summary {
  position: sticky;
  top: 76px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sm-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sm-summary-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: var(--sm-text-secondary);
}

.sm-summary-total {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
}

.sm-summary-total strong {
  font-size: 24px;
}

.sm-submit {
  width: 100%;
  margin-left: 0 !important;
}

@media (max-width: 900px) {
  .sm-checkout {
    grid-template-columns: 1fr;
  }

  .sm-summary {
    position: static;
  }

  .sm-line {
    flex-wrap: wrap;
  }
}
</style>
