<script setup lang="ts">
/**
 * 聊天输入区：发送 / 停止生成 / 转人工入口。
 * Enter 发送、Shift+Enter 换行；流式生成时输入框禁用但保留草稿。
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
    <div class="sm-composer-box">
      <textarea
        v-model="draft"
        class="sm-composer-input"
        rows="1"
        maxlength="4000"
        placeholder="问商品、查订单、问退换货政策…"
        aria-label="消息输入框"
        :disabled="disabled || streaming"
        @keydown.enter.exact.prevent="onSend"
      />
      <div class="sm-composer-actions">
        <ElButton
          v-if="!streaming"
          class="sm-send"
          type="primary"
          circle
          :disabled="!canSend"
          aria-label="发送"
          @click="onSend"
        >
          ↑
        </ElButton>
        <ElButton v-else class="sm-stop" type="warning" plain @click="emit('stop')">停止</ElButton>
      </div>
    </div>
    <div class="sm-composer-foot">
      <span class="sm-muted">
        Enter 发送 · Shift + Enter 换行 · 价格库存来自实时数据
      </span>
      <ElButton size="small" text type="primary" :disabled="disabled" @click="emit('handoff')">
        转人工客服
      </ElButton>
    </div>
  </div>
</template>

<style scoped>
.sm-composer {
  border-top: 1px solid var(--sm-border);
  background: var(--sm-surface);
  padding: 12px 18px 10px;
}

.sm-composer-box {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding: 6px 6px 6px 14px;
  border: 1.5px solid var(--sm-border);
  border-radius: 18px;
  background: var(--sm-surface);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.sm-composer-box:focus-within {
  border-color: var(--sm-primary);
  box-shadow: 0 0 0 4px rgb(59 91 253 / 10%);
}

.sm-composer-input {
  flex: 1;
  resize: none;
  min-height: 40px;
  max-height: 130px;
  padding: 9px 0;
  border: none;
  outline: none;
  background: transparent;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  color: var(--sm-text);
}

.sm-composer-actions {
  display: flex;
  gap: 8px;
  flex: none;
}

.sm-send {
  width: 38px;
  height: 38px;
  font-size: 17px;
  font-weight: 700;
}

.sm-composer-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 6px;
  padding: 0 4px;
}

@media (max-width: 768px) {
  .sm-composer {
    padding: 10px 12px 8px;
  }

  .sm-composer-foot .sm-muted {
    display: none;
  }

  .sm-composer-foot {
    justify-content: flex-end;
  }
}
</style>
