<script setup lang="ts">
/**
 * 统一状态块：加载 / 空 / 错误。
 * 错误使用稳定中文文案（ApiError.message），不展示 trace 或堆栈。
 *
 * ``stretch`` 用于「插槽内容自带滚动容器」的页面（如聊天线程）：根元素变成
 * flex 纵向布局并吃满父级剩余高度，让子元素的 ``overflow-y: auto`` 能真正
 * 生效。默认关闭——普通列表页保持原有的自然高度行为。
 */

import { ElAlert, ElButton, ElEmpty, ElSkeleton } from 'element-plus'

import type { ApiError } from '@/api/errors'

defineProps<{
  loading?: boolean
  error?: ApiError | null
  empty?: boolean
  emptyText?: string
  loadingText?: string
  stretch?: boolean
}>()

const emit = defineEmits<{ (e: 'retry'): void }>()
</script>

<template>
  <div class="sm-state" :class="{ 'sm-state-stretch': stretch }">
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
.sm-state {
  /* 普通页面：自然高度，块级布局不变。 */
}

.sm-state-stretch {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.sm-state-loading {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sm-state-error {
  margin: 8px 0;
}
</style>
