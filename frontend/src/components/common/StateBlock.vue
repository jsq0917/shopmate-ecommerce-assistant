<script setup lang="ts">
/**
 * 统一状态块：加载 / 空 / 错误。
 * 错误使用稳定中文文案（ApiError.message），不展示 trace 或堆栈。
 */

import { ElAlert, ElButton, ElEmpty, ElSkeleton } from 'element-plus'

import type { ApiError } from '@/api/errors'

defineProps<{
  loading?: boolean
  error?: ApiError | null
  empty?: boolean
  emptyText?: string
  loadingText?: string
}>()

const emit = defineEmits<{ (e: 'retry'): void }>()
</script>

<template>
  <div class="sm-state">
    <div v-if="loading" class="sm-state-loading">
      <ElSkeleton :rows="3" animated />
      <p class="sm-muted">{{ loadingText ?? '加载中…' }}</p>
    </div>

    <ElAlert
      v-else-if="error"
      class="sm-state-error"
      type="error"
      :closable="false"
      show-icon
      :title="error.message"
    >
      <template v-if="error.retryable" #default>
        <ElButton size="small" type="primary" @click="emit('retry')">重试</ElButton>
      </template>
    </ElAlert>

    <ElEmpty v-else-if="empty" :description="emptyText ?? '暂无数据'" />

    <slot v-else />
  </div>
</template>

<style scoped>
.sm-state-loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sm-state-error {
  margin: 8px 0;
}
</style>
