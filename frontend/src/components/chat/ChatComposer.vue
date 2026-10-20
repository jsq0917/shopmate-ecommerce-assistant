<script setup lang="ts">
/**
 * 聊天输入区：发送 / 停止生成 / 转人工入口。
 */

import { computed, ref } from 'vue'
import { ElButton } from 'element-plus'

const props = defineProps<{
  streaming: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'stop'): void
  (e: 'handoff'): void
}>()

const draft = ref('')

const canSend = computed(() => !props.streaming && !props.disabled && draft.value.trim().length > 0)

function onSend(): void {
  if (!canSend.value) return
  const text = draft.value.trim()
  draft.value = ''
  emit('send', text)
}
</script>

<template>
  <div class="sm-composer">
    <div class="sm-composer-row">
      <textarea
        v-model="draft"
        class="sm-composer-input"
        rows="2"
        maxlength="4000"
        placeholder="输入问题，例如：预算 300 元以内、适合通勤的降噪耳机（Enter 发送，Shift+Enter 换行）"
        aria-label="消息输入框"
        :disabled="disabled || streaming"
        @keydown.enter.exact.prevent="onSend"
      />
      <div class="sm-composer-actions">
        <ElButton v-if="!streaming" type="primary" :disabled="!canSend" @click="onSend">发送</ElButton>
        <ElButton v-else type="warning" @click="emit('stop')">停止生成</ElButton>
        <ElButton :disabled="disabled" @click="emit('handoff')">转人工</ElButton>
      </div>
    </div>
    <p class="sm-muted sm-composer-hint">
      价格、库存、订单与政策依据由系统从受控数据源实时获取；回答仅供参考，不构成退款或赔偿承诺。
    </p>
  </div>
</template>

<style scoped>
.sm-composer {
  border-top: 1px solid var(--sm-border);
  background: var(--sm-surface);
  padding: 10px 16px;
}

.sm-composer-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.sm-composer-input {
  flex: 1;
  resize: vertical;
  min-height: 48px;
  max-height: 140px;
  padding: 8px 10px;
  border: 1px solid var(--sm-border);
  border-radius: 8px;
  font-family: inherit;
  font-size: 14px;
}

.sm-composer-actions {
  display: flex;
  gap: 8px;
  flex: none;
}

.sm-composer-hint {
  margin: 6px 0 0;
}

@media (max-width: 768px) {
  .sm-composer-row {
    flex-direction: column;
    align-items: stretch;
  }

  .sm-composer-actions {
    justify-content: flex-end;
  }
}
</style>
