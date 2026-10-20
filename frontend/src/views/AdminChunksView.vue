<script setup lang="ts">
/**
 * 知识单元管理：按文档预览 chunk、编辑文本、启用/停用、软删除。
 * 编辑需填写 change_reason；文本修改后 reindex_required=true（服务端返回）。
 */

import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElAlert, ElButton, ElDialog, ElInput, ElMessageBox, ElOption, ElSelect, ElSwitch, ElTable, ElTableColumn } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { adminApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { ChunkListItem } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const route = useRoute()

const documents = ref<{ document_id: string; title: string }[]>([])
const documentId = ref('')
const chunks = ref<ChunkListItem[]>([])
const loading = ref(false)
const error = ref<ApiError | null>(null)
const actionError = ref<ApiError | null>(null)
const actionNotice = ref('')

const editDialog = ref(false)
const editing = ref<ChunkListItem | null>(null)
const editText = ref('')
const editEnabled = ref(true)
const editReason = ref('')
const saving = ref(false)

const canSave = computed(() => editReason.value.trim().length > 0 && !saving.value)

// ElTable 插槽的 row 为 DefaultRow（结构未知），传给强类型处理函数前收窄为 DTO。
const asChunk = (row: unknown): ChunkListItem => row as ChunkListItem

async function loadDocuments(): Promise<void> {
  try {
    const data = await adminApi.documents()
    documents.value = data.items.map((item) => ({ document_id: item.document_id, title: item.title }))
    const queryId = typeof route.query.document_id === 'string' ? route.query.document_id : ''
    if (queryId && documents.value.some((item) => item.document_id === queryId)) {
      documentId.value = queryId
    } else if (documents.value.length) {
      documentId.value = documents.value[0].document_id
    }
    if (documentId.value) await loadChunks()
  } catch (caught) {
    error.value = toApiError(caught)
  }
}

async function loadChunks(): Promise<void> {
  if (!documentId.value) return
  loading.value = true
  error.value = null
  try {
    const data = await adminApi.chunks({ document_id: documentId.value, limit: 100 })
    chunks.value = data.items
  } catch (caught) {
    error.value = toApiError(caught)
    chunks.value = []
  } finally {
    loading.value = false
  }
}

function openEdit(chunk: ChunkListItem): void {
  editing.value = chunk
  editText.value = chunk.text
  editEnabled.value = chunk.is_enabled
  editReason.value = ''
  editDialog.value = true
}

async function saveEdit(): Promise<void> {
  if (!editing.value || !canSave.value) return
  saving.value = true
  actionError.value = null
  actionNotice.value = ''
  try {
    const result = await adminApi.patchChunk(editing.value.chunk_id, {
      text: editText.value,
      is_enabled: editEnabled.value,
      change_reason: editReason.value.trim(),
    })
    actionNotice.value = result.reindex_required
      ? '已保存，需要重新入库后生效。'
      : '已保存。'
    editDialog.value = false
    await loadChunks()
  } catch (caught) {
    actionError.value = toApiError(caught)
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(chunk: ChunkListItem, next: boolean): Promise<void> {
  actionError.value = null
  actionNotice.value = ''
  try {
    const result = await adminApi.patchChunk(chunk.chunk_id, {
      is_enabled: next,
      change_reason: next ? '运营重新启用知识单元' : '运营停用知识单元',
    })
    actionNotice.value = next ? '已启用。' : '已停用，不再参与检索。'
    if (result.reindex_required) actionNotice.value += '需要重新入库后生效。'
    await loadChunks()
  } catch (caught) {
    actionError.value = toApiError(caught)
  }
}

async function removeChunk(chunk: ChunkListItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `软删除第 ${chunk.chunk_index + 1} 个知识单元？历史版本保留，可追溯。`,
      '删除知识单元',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  actionError.value = null
  try {
    await adminApi.disableChunk(chunk.chunk_id)
    actionNotice.value = '已软删除。'
    await loadChunks()
  } catch (caught) {
    actionError.value = toApiError(caught)
  }
}

onMounted(loadDocuments)
</script>

<template>
  <div class="sm-page">
    <div class="sm-between">
      <h2 class="sm-page-title">知识单元管理</h2>
      <ElSelect v-model="documentId" placeholder="选择文档" style="width: 16rem" @change="loadChunks">
        <ElOption v-for="doc in documents" :key="doc.document_id" :label="doc.title" :value="doc.document_id" />
      </ElSelect>
    </div>

    <ElAlert v-if="actionNotice" class="sm-alert" type="success" :closable="false" show-icon :title="actionNotice" />
    <ElAlert v-if="actionError" class="sm-alert" type="error" :closable="false" show-icon :title="actionError.message" />

    <StateBlock
      :loading="loading && !chunks.length"
      :error="error"
      :empty="!loading && !error && chunks.length === 0"
      empty-text="该文档暂无知识单元。"
      @retry="loadChunks"
    >
      <ElTable :data="chunks" size="small" border style="margin-top: 12px">
        <ElTableColumn label="序号" width="70">
          <template #default="{ row }">#{{ row.chunk_index + 1 }}</template>
        </ElTableColumn>
        <ElTableColumn label="标题路径" min-width="180">
          <template #default="{ row }">{{ row.heading_path.join(' / ') || '--' }}</template>
        </ElTableColumn>
        <ElTableColumn label="页码" width="70">
          <template #default="{ row }">{{ row.page_no ?? '--' }}</template>
        </ElTableColumn>
        <ElTableColumn label="内容预览" min-width="280">
          <template #default="{ row }">
            <span class="sm-chunk-text" :title="row.text">{{ row.text }}</span>
          </template>
        </ElTableColumn>
        <ElTableColumn label="Token" width="80">
          <template #default="{ row }">{{ row.token_count }}</template>
        </ElTableColumn>
        <ElTableColumn label="启用" width="90">
          <template #default="{ row }">
            <ElSwitch
              :model-value="row.is_enabled"
              :active-text="row.is_enabled ? '是' : '否'"
              inline-prompt
              style="--el-switch-on-color: var(--sm-primary)"
              @change="(next: string | number | boolean) => toggleEnabled(asChunk(row), Boolean(next))"
            />
          </template>
        </ElTableColumn>
        <ElTableColumn label="更新时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </ElTableColumn>
        <ElTableColumn label="操作" min-width="120">
          <template #default="{ row }">
            <ElButton size="small" text type="primary" @click="openEdit(asChunk(row))">编辑</ElButton>
            <ElButton size="small" text type="danger" @click="removeChunk(asChunk(row))">删除</ElButton>
          </template>
        </ElTableColumn>
      </ElTable>
    </StateBlock>

    <ElDialog v-model="editDialog" title="编辑知识单元" width="min(40rem, 94vw)">
      <template v-if="editing">
        <p class="sm-muted">
          文档 <span class="sm-mono">{{ editing.document_id }}</span> · 版本 <span class="sm-mono">{{ editing.version_id }}</span>
        </p>
        <ElInput v-model="editText" type="textarea" :rows="10" maxlength="20000" show-word-limit />
        <div class="sm-between sm-edit-row">
          <ElSwitch v-model="editEnabled" active-text="参与检索" inactive-text="停用" />
          <ElInput v-model="editReason" placeholder="修改原因（必填，1-200 字）" maxlength="200" style="max-width: 18rem" />
        </div>
      </template>
      <ElAlert v-if="actionError" type="error" :closable="false" show-icon :title="actionError.message" />
      <template #footer>
        <ElButton @click="editDialog = false">取消</ElButton>
        <ElButton type="primary" :loading="saving" :disabled="!canSave" @click="saveEdit">保存</ElButton>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0;
  font-size: 18px;
}

.sm-alert {
  margin: 12px 0;
}

.sm-chunk-text {
  display: inline-block;
  max-width: 30rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: bottom;
}

.sm-edit-row {
  margin-top: 12px;
}
</style>
