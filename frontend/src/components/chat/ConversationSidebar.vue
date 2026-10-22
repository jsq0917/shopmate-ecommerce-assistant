<script setup lang="ts">
/**
 * 会话侧栏：选择、重命名、软删除（新建入口由外层容器提供）。
 */

import { ref } from 'vue'
import { ElInput, ElMessageBox } from 'element-plus'

import type { ConversationItem } from '@/api/types'

defineProps<{
  conversations: ConversationItem[]
  activeId: string | null
  loading?: boolean
  error?: unknown
}>()

const emit = defineEmits<{
  (e: 'create'): void
  (e: 'select', id: string): void
  (e: 'rename', id: string, title: string): void
  (e: 'remove', id: string): void
}>()

const editingId = ref<string | null>(null)
const editingTitle = ref('')

function startRename(conversation: ConversationItem): void {
  editingId.value = conversation.id
  editingTitle.value = conversation.title
}

function commitRename(): void {
  const id = editingId.value
  const title = editingTitle.value.trim()
  editingId.value = null
  if (id && title) emit('rename', id, title)
}

async function confirmRemove(conversation: ConversationItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `删除会话“${conversation.title}”？删除后可在审计中追溯，列表中不再显示。`,
      '删除会话',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  emit('remove', conversation.id)
}
</script>

<template>
  <p v-if="!conversations.length" class="sm-conversation-empty">暂无会话</p>
  <ul v-else class="sm-conversation-list" aria-label="会话列表">
    <li
      v-for="conversation in conversations"
      :key="conversation.id"
      class="sm-conversation-item"
      :class="{ 'sm-conversation-active': conversation.id === activeId }"
    >
      <template v-if="editingId === conversation.id">
        <ElInput
          v-model="editingTitle"
          size="small"
          maxlength="120"
          @keyup.enter="commitRename"
          @blur="commitRename"
        />
      </template>
      <template v-else>
        <span class="sm-conversation-dot" aria-hidden="true" />
        <button type="button" class="sm-conversation-select" @click="emit('select', conversation.id)">
          <span class="sm-conversation-name" :title="conversation.title">{{ conversation.title }}</span>
        </button>
        <span class="sm-conversation-actions">
          <button type="button" class="sm-icon-button" aria-label="重命名会话" @click="startRename(conversation)">
            ✎
          </button>
          <button type="button" class="sm-icon-button sm-icon-danger" aria-label="删除会话" @click="confirmRemove(conversation)">
            ✕
          </button>
        </span>
      </template>
    </li>
  </ul>
</template>

<style scoped>
.sm-conversation-empty {
  margin: 0;
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--sm-text-tertiary);
}

.sm-conversation-list {
  list-style: none;
  margin: 0;
  padding: 4px 8px 12px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
}

.sm-conversation-item {
  display: flex;
  align-items: center;
  gap: 6px;
  border-radius: 9px;
  padding: 2px 6px 2px 8px;
  transition: background 0.15s ease;
}

.sm-conversation-item:hover {
  background: var(--sm-bg);
}

.sm-conversation-active {
  background: var(--sm-primary-soft);
}

.sm-conversation-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--sm-border-strong);
  flex: none;
}

.sm-conversation-active .sm-conversation-dot {
  background: var(--sm-primary);
}

.sm-conversation-select {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  text-align: left;
  padding: 8px 0;
  cursor: pointer;
  font-size: 13px;
  color: var(--sm-text);
}

.sm-conversation-name {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sm-conversation-actions {
  flex: none;
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.sm-conversation-item:hover .sm-conversation-actions {
  opacity: 1;
}

.sm-icon-button {
  border: none;
  background: none;
  cursor: pointer;
  color: var(--sm-text-tertiary);
  font-size: 12px;
  padding: 2px 5px;
  border-radius: 5px;
}

.sm-icon-button:hover {
  background: var(--sm-surface);
  color: var(--sm-primary-dark);
}

.sm-icon-danger:hover {
  color: var(--sm-danger);
}
</style>
