<script setup lang="ts">
/**
 * 回答质量标记（docs/06-api.md 第 12 节）：
 * correct / incorrect / needs_knowledge。标记只进入评测流程，
 * 不修改知识版本、检索结果或模型参数。
 */

import { computed, ref } from 'vue'
import { ElAlert, ElButton, ElInput, ElOption, ElSelect } from 'element-plus'

import { supportApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import { qualityLabel } from '@/utils/format'

const props = defineProps<{ assistantMessageId: string }>()

const emit = defineEmits<{ (e: 'labeled'): void }>()

const label = ref<'correct' | 'incorrect' | 'needs_knowledge'>('correct')
const reason = ref('')
const submitting = ref(false)
const error = ref<ApiError | null>(null)
const success = ref(false)

const canSubmit = computed(
  () =>
    !submitting.value &&
    (label.value === 'correct' || reason.value.trim().length > 0),
);

async function submit(): Promise<void> {
  if (!canSubmit.value) return
  submitting.value = true
  error.value = null
  success.value = false
  try {
    await supportApi.qualityLabel(props.assistantMessageId, {
      label: label.value,
      reason_summary: reason.value.trim() || null,
    })
    success.value = true
    reason.value = ''
    emit('labeled')
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="sm-quality">
    <h4 class="sm-section-title">回答质量标记</h4>
    <div class="sm-quality-row">
      <ElSelect v-model="label" style="width: 10rem">
        <ElOption
          v-for="option in ['correct', 'incorrect', 'needs_knowledge']"
          :key="option"
          :label="qualityLabel(option)"
          :value="option"
        />
      </ElSelect>
      <ElInput
        v-model="reason"
        placeholder="标记原因摘要（incorrect / needs_knowledge 必填）"
        maxlength="200"
        style="max-width: 20rem"
      />
      <ElButton size="small" type="primary" :loading="submitting" :disabled="!canSubmit" @click="submit">
        提交标记
      </ElButton>
    </div>
    <ElAlert v-if="error" type="error" :closable="false" show-icon :title="error.message" class="sm-quality-alert" />
    <ElAlert
      v-if="success"
      type="success"
      :closable="false"
      show-icon
      title="已记录标记，进入评测样本流程。"
      class="sm-quality-alert"
    />
  </div>
</template>

<style scoped>
.sm-section-title {
  margin: 0 0 8px;
  font-size: 14px;
}

.sm-quality-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.sm-quality-alert {
  margin-top: 8px;
}
</style>
