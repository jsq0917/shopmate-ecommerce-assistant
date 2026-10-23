<script setup lang="ts">
/**
 * 会话级知识库多选（课程任务书硬性要求：知识库可选一个或多个）。
 *
 * 语义（与后端一致）：
 * - 选中一个或多个 → 检索只在这些知识库里进行；
 * - 空选 → 不限制，检索全部可见知识库（等同改造前的行为），此时给明确提示，避免用户
 *   误以为「没选就什么都搜不到」；
 * - 切换只影响后续消息，历史消息的引用不会被改写。
 */

import { computed } from 'vue'
import { ElOption, ElSelect } from 'element-plus'

import type { KnowledgeBaseOption } from '@/api/types'

const props = defineProps<{
  options: KnowledgeBaseOption[]
  modelValue: string[]
  disabled?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
  (e: 'change', value: string[]): void
}>()

const selected = computed({
  get: () => props.modelValue,
  set: (value: string[]) => emit('update:modelValue', value),
})

const isEmpty = computed(() => props.modelValue.length === 0)
const placeholder = computed(() =>
  props.options.length ? '全部知识库（默认）' : '当前店铺暂无知识库',
)

function onChange(value: string[]): void {
  emit('change', value)
}
</script>

<template>
  <div class="sm-kb-select" data-testid="kb-select">
    <span class="sm-kb-label">知识库</span>
    <ElSelect
      v-model="selected"
      class="sm-kb-input"
      data-testid="kb-select-input"
      multiple
      collapse-tags
      collapse-tags-tooltip
      clearable
      size="small"
      :placeholder="placeholder"
      :disabled="disabled || loading || !options.length"
      :loading="loading"
      @change="onChange"
    >
      <ElOption
        v-for="item in options"
        :key="item.id"
        :label="item.name"
        :value="item.id"
      />
    </ElSelect>
    <span v-if="isEmpty" class="sm-kb-hint" data-testid="kb-hint">
      未选择知识库：将检索全部可见知识库
    </span>
    <span v-else class="sm-kb-hint sm-kb-hint-active" data-testid="kb-hint-selected">
      仅检索所选 {{ modelValue.length }} 个知识库
    </span>
  </div>
</template>

<style scoped>
.sm-kb-select {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.sm-kb-label {
  font-size: 12px;
  color: var(--sm-text-muted, #6b7280);
  white-space: nowrap;
}

.sm-kb-input {
  width: 220px;
  max-width: 46vw;
}

.sm-kb-hint {
  font-size: 12px;
  color: var(--sm-text-muted, #6b7280);
  white-space: nowrap;
}

.sm-kb-hint-active {
  color: var(--sm-primary, #2563eb);
}
</style>
