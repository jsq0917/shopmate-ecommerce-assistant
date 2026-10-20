<script setup lang="ts">
/**
 * 转人工对话框（消费者侧）。写操作带 Idempotency-Key；同一意图重复提交
 * 只会得到同一工单（幂等重放），不会创建第二条。
 */

import { computed, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElOption, ElSelect } from 'element-plus'

import { handoffApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { CreateHandoffData } from '@/api/types'
import { HANDOFF_REASON_OPTIONS, newUuid } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  conversationId: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', ticket: CreateHandoffData): void
}>()

const reasonCode = ref('USER_REQUESTS_HUMAN')
const summary = ref('')
const submitting = ref(false)
const error = ref<ApiError | null>(null)
const result = ref<CreateHandoffData | null>(null)

const canSubmit = computed(() => summary.value.trim().length > 0 && !submitting.value)

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      reasonCode.value = 'USER_REQUESTS_HUMAN'
      summary.value = ''
      error.value = null
      result.value = null
    }
  },
)

async function onSubmit(): Promise<void> {
  if (!props.conversationId || !canSubmit.value) return
  submitting.value = true
  error.value = null
  try {
    const ticket = await handoffApi.create(
      {
        conversation_id: props.conversationId,
        reason_code: reasonCode.value,
        summary_redacted: summary.value.trim().slice(0, 500),
      },
      newUuid(),
    )
    result.value = ticket
    emit('created', ticket)
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    submitting.value = false
  }
}

function close(): void {
  emit('update:modelValue', false)
}
</script>

<template>
  <ElDialog :model-value="modelValue" title="转人工客服" width="min(30rem, 94vw)" @update:model-value="emit('update:modelValue', $event)">
    <ElAlert
      v-if="result"
      type="success"
      :closable="false"
      show-icon
      title="已创建人工工单"
    >
      <p>工单号：<span class="sm-mono">{{ result.ticket_id }}</span></p>
      <p>队列：{{ result.queue }} · 优先级 P{{ result.priority }}</p>
      <p>{{ result.expected_response }}</p>
      <p class="sm-muted">这不是退款或赔偿承诺；客服会按队列顺序跟进。</p>
    </ElAlert>

    <template v-else>
      <p class="sm-muted">请选择原因并简要描述问题（不要填写手机号、地址等个人信息）。提交后将由人工客服跟进。</p>
      <ElForm label-position="top">
        <ElFormItem label="转人工原因">
          <ElSelect v-model="reasonCode" style="width: 100%">
            <ElOption
              v-for="option in HANDOFF_REASON_OPTIONS"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="问题描述（最多 500 字，不含个人信息）">
          <ElInput
            v-model="summary"
            type="textarea"
            :rows="4"
            maxlength="500"
            show-word-limit
            placeholder="例如：对退货政策有疑问，需要客服解释"
          />
        </ElFormItem>
      </ElForm>

      <ElAlert v-if="error" type="error" :closable="false" show-icon :title="error.message" />
    </template>

    <template #footer>
      <ElButton @click="close">{{ result ? '关闭' : '取消' }}</ElButton>
      <ElButton v-if="!result" type="primary" :loading="submitting" :disabled="!canSubmit" @click="onSubmit">
        提交工单
      </ElButton>
    </template>
  </ElDialog>
</template>
