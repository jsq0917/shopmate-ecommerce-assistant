<script setup lang="ts">
/**
 * 会话侧栏：新建、选择、重命名、软删除。
 */

import { ref } from 'vue'
import { ElButton, ElEmpty, ElInput, ElMessageBox } from 'element-plus'

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
    await ElMessageBox.confirm(`删除会话“${conversation.title}”？删除后可在审计中追溯，列表中不再显示。`, '删除会话', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  emit('remove', conversation.id)
}
</script>

<template>
  <aside class="sm-conversations" aria-label="会话列表">
    <div class="sm-conversations-head">
      <span class="sm-conversations-title">会话</span>
      <ElButton size="small" type="primary" @click="emit('create')">新建</ElButton>
    </div>

    <ElEmpty v-if="!loading && !conversations.length" description="暂无会话" :image-size="48" />

    <ul v-else class="sm-conversation-list">
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
          <button type="button" class="sm-conversation-select" @click="emit('select', conversation.id)">
            <span class="sm-conversation-name" :title="conversation.title">{{ conversation.title }}</span>
          </button>
          <span class="sm-conversation-actions">
            <ElButton size="small" text type="primary" aria-label="重命名会话" @click="startRename(conversation)">
              ✎
            </ElButton>
            <ElButton size="small" text type="danger" aria-label="删除会话" @click="confirmRemove(conversation)">
              🗑
            </ElButton>
          </span>
        </template>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.sm-conversations {
  width: 240px;
  flex: none;
  border-right: 1px solid var(--sm-border);
  background: var(--sm-surface);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sm-conversations-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--sm-border);
}

.sm-conversations-title {
  font-weight: 700;
}

.sm-conversation-list {
  list-style: none;
  margin: 0;
  padding: 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sm-conversation-item {
  display: flex;
  align-items: center;
  gap: 4px;
  border-radius: 8px;
  padding: 2px 4px;
}

.sm-conversation-item:hover {
  background: var(--sm-bg);
}

.sm-conversation-active {
  background: rgb(31 122 92 / 10%);
}

.sm-conversation-select {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  text-align: left;
  padding: 6px 4px;
  cursor: pointer;
  font-size: 13px;
  color: inherit;
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
}

@media (max-width: 768px) {
  .sm-conversations {
    width: 100%;
    border-right: none;
    border-bottom: 1px solid var(--sm-border);
    max-height: 40vh;
  }
}
</style>
