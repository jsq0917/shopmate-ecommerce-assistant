<script setup lang="ts">
/**
 * 退货向导：资格检查 -> 用户明确确认 -> 幂等提交。
 *
 * 业务铁律 2：LLM/前端都不能代替规则决策；创建申请只是 submitted，
 * 不等于退款成功（refund_status 恒为 not_created）。
 */

import { computed, ref } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElForm, ElFormItem, ElOption, ElSelect } from 'element-plus'

import { returnsApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type {
  CreateReturnData,
  OrderItemSummary,
  ReturnEligibilityData,
  ReturnReasonCode,
} from '@/api/types'
import {
  RETURN_REASON_OPTIONS,
  decisionLabel,
  formatDateTime,
  formatMoney,
  newUuid,
} from '@/utils/format'

const props = defineProps<{
  orderId: string
  items: OrderItemSummary[]
}>()

const emit = defineEmits<{ (e: 'created', data: CreateReturnData): void }>()

const orderItemId = ref('')
const reasonCode = ref<ReturnReasonCode>('SIZE_OR_FIT')
const confirmed = ref(false)
const checking = ref(false)
const eligibility = ref<ReturnEligibilityData | null>(null)
const checkError = ref<ApiError | null>(null)
const submitting = ref(false)
const submitError = ref<ApiError | null>(null)
const created = ref<CreateReturnData | null>(null)

const canCheck = computed(() => orderItemId.value !== '' && !checking.value)
const canSubmit = computed(
  () =>
    eligibility.value?.eligible === true &&
    confirmed.value &&
    !submitting.value &&
    Boolean(eligibility.value.eligibility_token),
)

async function check(): Promise<void> {
  if (!canCheck.value) return
  checking.value = true
  checkError.value = null
  eligibility.value = null
  created.value = null
  confirmed.value = false
  try {
    eligibility.value = await returnsApi.eligibility({
      order_id: props.orderId,
      order_item_id: orderItemId.value,
      reason_code: reasonCode.value,
    })
  } catch (caught) {
    checkError.value = toApiError(caught)
  } finally {
    checking.value = false
  }
}

async function submit(): Promise<void> {
  if (!canSubmit.value || !eligibility.value?.eligibility_token) return
  submitting.value = true
  submitError.value = null
  try {
    const data = await returnsApi.create(
      {
        order_id: props.orderId,
        order_item_id: orderItemId.value,
        reason_code: reasonCode.value,
        eligibility_token: eligibility.value.eligibility_token,
        confirmed: true,
      },
      newUuid(),
    )
    created.value = data
    emit('created', data)
  } catch (caught) {
    submitError.value = toApiError(caught)
  } finally {
    submitting.value = false
  }
}

const ruleVersion = computed(() => eligibility.value?.rule_version ?? '--')
</script>

<template>
  <div class="sm-return">
    <h4 class="sm-return-title">申请退货</h4>
    <p class="sm-muted">退货资格由确定性规则判定；提交申请不代表退款成功，退款需审核后另行处理。</p>

    <ElForm v-if="!created" label-position="top">
      <ElFormItem label="选择要退货的商品">
        <ElSelect v-model="orderItemId" placeholder="请选择订单商品" style="width: 100%">
          <ElOption
            v-for="item in items"
            :key="item.id"
            :label="`${item.title}（${item.sku}）× ${item.quantity} · ${formatMoney(item.unit_price_cents, 'CNY')}`"
            :value="item.id"
          />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="退货原因">
        <ElSelect v-model="reasonCode" style="width: 100%">
          <ElOption
            v-for="option in RETURN_REASON_OPTIONS"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </ElSelect>
      </ElFormItem>
      <ElButton type="primary" :loading="checking" :disabled="!canCheck" @click="check">
        检查退货资格
      </ElButton>
    </ElForm>

    <ElAlert v-if="checkError" class="sm-return-alert" type="error" :closable="false" show-icon :title="checkError.message" />

    <div v-if="eligibility" class="sm-return-result">
      <ElAlert
        :type="eligibility.eligible ? 'success' : eligibility.needs_manual_review ? 'warning' : 'info'"
        :closable="false"
        show-icon
        :title="`资格结论：${decisionLabel(eligibility.decision)}`"
      >
        <p>结果码：<span class="sm-mono">{{ eligibility.decision_code }}</span> · 规则版本 {{ ruleVersion }}</p>
        <p v-if="eligibility.deadline_at">退货截止：{{ formatDateTime(eligibility.deadline_at) }}</p>
        <p v-if="eligibility.matched_rule_codes.length">命中规则：{{ eligibility.matched_rule_codes.join('、') }}</p>
        <p v-if="eligibility.required_materials.length">需要准备：{{ eligibility.required_materials.join('、') }}</p>
        <p>下一步：{{ eligibility.next_action }}</p>
        <p v-if="eligibility.needs_manual_review" class="sm-return-warn">
          该情况需要人工审核，不会自动创建申请；你可以在聊天页使用“转人工”。
        </p>
      </ElAlert>

      <div v-if="eligibility.eligible" class="sm-return-confirm">
        <ElCheckbox v-model="confirmed">
          我确认提交退货申请，并了解：提交仅生成申请，不等于退款成功；退款需审核后处理。
        </ElCheckbox>
        <div>
          <ElButton type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
            提交退货申请
          </ElButton>
        </div>
      </div>
    </div>

    <ElAlert v-if="submitError" class="sm-return-alert" type="error" :closable="false" show-icon :title="submitError.message" />

    <ElAlert v-if="created" class="sm-return-alert" type="success" :closable="false" show-icon title="退货申请已提交">
      <p>申请单号：<span class="sm-mono">{{ created.return_request_id }}</span></p>
      <p>状态：{{ created.status }}（待审核） · 退款状态：{{ created.refund_status }}</p>
      <p v-if="created.required_materials.length">请准备：{{ created.required_materials.join('、') }}</p>
      <p class="sm-muted">{{ created.notice }}</p>
    </ElAlert>
  </div>
</template>

<style scoped>
.sm-return {
  border: 1px solid var(--sm-border);
  border-radius: var(--sm-radius);
  padding: 14px;
  background: var(--sm-surface);
}

.sm-return-title {
  margin: 0 0 4px;
  font-size: 15px;
}

.sm-return-alert {
  margin-top: 12px;
}

.sm-return-result {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sm-return-confirm {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sm-return-warn {
  color: var(--sm-warning);
}
</style>
