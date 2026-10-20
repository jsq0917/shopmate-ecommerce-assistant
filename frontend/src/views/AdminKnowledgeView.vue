<script setup lang="ts">
/**
 * 管理端知识库：知识库列表/创建、文档与解析状态、上传、重新入库。
 * 历史版本保留，重新导入创建新版本（PRD F-21/F-22）。
 */

import { onMounted, ref } from 'vue'
import { ElAlert, ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElMessageBox, ElOption, ElSelect, ElTable, ElTableColumn, ElTag } from 'element-plus'

import DocumentUploadDialog from '@/components/admin/DocumentUploadDialog.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import { adminApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type {
  DocumentListItem,
  KnowledgeBaseItem,
  UploadDocumentData,
} from '@/api/types'
import { docTypeLabel, formatDateTime, parseStatusLabel } from '@/utils/format'

const loading = ref(true)
const error = ref<ApiError | null>(null)
const knowledgeBases = ref<KnowledgeBaseItem[]>([])
const kbFilter = ref('')
const documents = ref<DocumentListItem[]>([])
const actionError = ref<ApiError | null>(null)
const actionNotice = ref('')
const kbDialog = ref(false)
const kbName = ref('')
const uploadVisible = ref(false)
const reindexingId = ref('')

// ElTable 插槽的 row 为 DefaultRow（结构未知），传给强类型处理函数前收窄为 DTO。
const asDocument = (row: unknown): DocumentListItem => row as DocumentListItem

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [kbData, docData] = await Promise.all([
      adminApi.knowledgeBases(),
      adminApi.documents(kbFilter.value || undefined),
    ])
    knowledgeBases.value = kbData.items
    documents.value = docData.items
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    loading.value = false
  }
}

async function createKnowledgeBase(): Promise<void> {
  if (!kbName.value.trim()) return
  try {
    await adminApi.createKnowledgeBase({ name: kbName.value.trim() })
    kbDialog.value = false
    kbName.value = ''
    actionNotice.value = '知识库已创建。'
    await load()
  } catch (caught) {
    actionError.value = toApiError(caught)
  }
}

async function reindex(document: DocumentListItem): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `对《${document.title}》重新入库？将创建新版本并保留历史版本。`,
      '重新入库',
      { confirmButtonText: '开始', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  reindexingId.value = document.document_id
  actionError.value = null
  actionNotice.value = ''
  try {
    await adminApi.reindexDocument(document.document_id)
    actionNotice.value = `已为《${document.title}》创建重新入库任务。`
    await load()
  } catch (caught) {
    actionError.value = toApiError(caught)
  } finally {
    reindexingId.value = ''
  }
}

function onUploaded(data: UploadDocumentData): void {
  uploadVisible.value = false
  actionNotice.value = `上传已接受，版本 ${data.version_id} 解析中。`
  void load()
}

function parseStatusType(status: string | null): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'ready') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'pending') return 'info'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div class="sm-page">
    <div class="sm-between">
      <h2 class="sm-page-title">知识库管理</h2>
      <div class="sm-row">
        <ElSelect v-model="kbFilter" placeholder="全部知识库" clearable style="width: 12rem" @change="load">
          <ElOption v-for="kb in knowledgeBases" :key="kb.id" :label="kb.name" :value="kb.id" />
        </ElSelect>
        <ElButton @click="kbDialog = true">新建知识库</ElButton>
        <ElButton type="primary" @click="uploadVisible = true">上传文档</ElButton>
      </div>
    </div>

    <ElAlert v-if="actionNotice" class="sm-alert" type="success" :closable="false" show-icon :title="actionNotice" />
    <ElAlert v-if="actionError" class="sm-alert" type="error" :closable="false" show-icon :title="actionError.message" />

    <div class="sm-card">
      <h3 class="sm-section-title">知识库</h3>
      <ElTable :data="knowledgeBases" size="small" border>
        <ElTableColumn prop="name" label="名称" min-width="160" />
        <ElTableColumn prop="locale" label="语言" min-width="90" />
        <ElTableColumn prop="region" label="地区" min-width="90" />
        <ElTableColumn prop="status" label="状态" min-width="90" />
        <ElTableColumn label="创建时间" min-width="150">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </ElTableColumn>
      </ElTable>
    </div>

    <div class="sm-card">
      <h3 class="sm-section-title">文档与解析状态</h3>
      <StateBlock
        :loading="loading && !documents.length"
        :error="error"
        :empty="!loading && !error && documents.length === 0"
        empty-text="暂无文档。"
        @retry="load"
      >
        <ElTable :data="documents" size="small" border>
          <ElTableColumn prop="title" label="标题" min-width="200" show-overflow-tooltip />
          <ElTableColumn label="类型" min-width="90">
            <template #default="{ row }">{{ docTypeLabel(row.doc_type) }}</template>
          </ElTableColumn>
          <ElTableColumn label="当前版本" min-width="110">
            <template #default="{ row }">{{ row.current_version ?? '--' }}</template>
          </ElTableColumn>
          <ElTableColumn label="解析状态" min-width="110">
            <template #default="{ row }">
              <ElTag size="small" :type="parseStatusType(row.parse_status)">{{ parseStatusLabel(row.parse_status) }}</ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="语言/地区" min-width="110">
            <template #default="{ row }">{{ row.locale }} / {{ row.region }}</template>
          </ElTableColumn>
          <ElTableColumn label="生效期" min-width="200">
            <template #default="{ row }">
              {{ row.effective_from ? formatDateTime(row.effective_from) : '--' }}
              ~
              {{ row.effective_to ? formatDateTime(row.effective_to) : '长期' }}
            </template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" min-width="150">
            <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
          </ElTableColumn>
          <ElTableColumn label="数据" min-width="80">
            <template #default="{ row }">
              <span v-if="row.is_synthetic" class="sm-synthetic-tag">合成</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="操作" min-width="150">
            <template #default="{ row }">
              <ElButton size="small" text type="primary" @click="$router.push(`/admin/chunks?document_id=${row.document_id}`)">
                知识单元
              </ElButton>
              <ElButton
                size="small"
                text
                type="primary"
                :loading="reindexingId === row.document_id"
                @click="reindex(asDocument(row))"
              >
                重新入库
              </ElButton>
            </template>
          </ElTableColumn>
        </ElTable>
      </StateBlock>
    </div>

    <DocumentUploadDialog v-model="uploadVisible" :knowledge-bases="knowledgeBases" @uploaded="onUploaded" />

    <ElDialog v-model="kbDialog" title="新建知识库" width="min(26rem, 94vw)">
      <ElForm label-position="top">
        <ElFormItem label="名称">
          <ElInput v-model="kbName" maxlength="160" placeholder="例如：售后政策库" />
        </ElFormItem>
      </ElForm>
      <template #footer>
        <ElButton @click="kbDialog = false">取消</ElButton>
        <ElButton type="primary" :disabled="!kbName.trim()" @click="createKnowledgeBase">创建</ElButton>
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

.sm-card {
  margin-bottom: 12px;
}

.sm-section-title {
  margin: 0 0 10px;
  font-size: 15px;
}

.sm-synthetic-tag {
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}
</style>
