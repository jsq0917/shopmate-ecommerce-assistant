<script setup lang="ts">
/**
 * 文档上传对话框（POST /admin/documents，multipart/form-data）。
 * 约束（docs/06-api.md 第 13 节）：单文件 ≤ 20 MiB，仅 PDF/DOCX/PPTX/MD/TXT；
 * effective_to 必须晚于 effective_from（前端做基础校验，服务端为准）。
 */

import { computed, ref, watch } from 'vue'
import { ElAlert, ElButton, ElDatePicker, ElDialog, ElForm, ElFormItem, ElInput, ElOption, ElSelect, ElUpload } from 'element-plus'
import type { UploadFile } from 'element-plus'

import { adminApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { DocumentType, KnowledgeBaseItem, UploadDocumentData } from '@/api/types'
import { docTypeLabel } from '@/utils/format'

const MAX_SIZE_MIB = 20
const IMAGE_MAX_MIB = 10
//: 图片同样只是「离线文档」的一种：入库时走 OCR（stage 20），因此扩展名白名单要与后端
//: `SUPPORTED_SUFFIXES` 保持一致，否则前端能选、后端 415。
const ALLOWED_EXTENSIONS = ['pdf', 'docx', 'pptx', 'md', 'txt', 'png', 'jpg', 'jpeg']
const ACCEPT = ALLOWED_EXTENSIONS.map((item) => `.${item}`).join(',')

const props = defineProps<{
  modelValue: boolean
  knowledgeBases: KnowledgeBaseItem[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'uploaded', data: UploadDocumentData): void
}>()

const knowledgeBaseId = ref('')
const title = ref('')
const docType = ref<DocumentType>('policy')
const locale = ref('zh-CN')
const region = ref('CN')
const effectiveFrom = ref('')
const effectiveTo = ref('')
const file = ref<File | null>(null)
const submitting = ref(false)
const error = ref<ApiError | null>(null)
const result = ref<UploadDocumentData | null>(null)

const docTypeOptions: DocumentType[] = ['policy', 'faq', 'manual', 'warranty', 'invoice', 'shipping', 'other']

const fileError = computed(() => {
  if (!file.value) return ''
  const extension = file.value.name.toLowerCase().split('.').pop() ?? ''
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `不支持的文件类型：.${extension}（仅支持 ${ACCEPT}）`
  }
  // 图片后端限 10 MiB（OCR 前要整图读入内存），文档仍是 20 MiB。
  const limit = ['png', 'jpg', 'jpeg'].includes(extension) ? IMAGE_MAX_MIB : MAX_SIZE_MIB
  if (file.value.size > limit * 1024 * 1024) {
    return `文件超过 ${limit} MiB 上限`
  }
  return ''
})

const canSubmit = computed(
  () =>
    knowledgeBaseId.value !== '' &&
    title.value.trim() !== '' &&
    effectiveFrom.value !== '' &&
    file.value !== null &&
    fileError.value === '' &&
    (!effectiveTo.value || effectiveTo.value > effectiveFrom.value) &&
    !submitting.value,
)

watch(
  () => props.modelValue,
  (visible) => {
    if (!visible) return
    knowledgeBaseId.value = props.knowledgeBases[0]?.id ?? ''
    title.value = ''
    docType.value = 'policy'
    locale.value = 'zh-CN'
    region.value = 'CN'
    effectiveFrom.value = ''
    effectiveTo.value = ''
    file.value = null
    error.value = null
    result.value = null
  },
)

function onFileChange(uploadFile: UploadFile): void {
  const raw = uploadFile.raw
  file.value = raw instanceof File ? raw : null
}

async function onSubmit(): Promise<void> {
  if (!canSubmit.value || !file.value) return
  submitting.value = true
  error.value = null
  try {
    const data = await adminApi.uploadDocument({
      knowledge_base_id: knowledgeBaseId.value,
      title: title.value.trim(),
      doc_type: docType.value,
      locale: locale.value.trim(),
      region: region.value.trim().toUpperCase(),
      effective_from: new Date(effectiveFrom.value).toISOString(),
      effective_to: effectiveTo.value ? new Date(effectiveTo.value).toISOString() : null,
      file: file.value,
    })
    result.value = data
    emit('uploaded', data)
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    submitting.value = false
  }
}

function close(): void {
  emit('update:modelValue', false)
}
</script>

<template>
  <ElDialog :model-value="modelValue" title="上传知识文档" width="min(34rem, 94vw)" @update:model-value="emit('update:modelValue', $event)">
    <ElAlert v-if="result" type="success" :closable="false" show-icon title="已创建新版本，后台解析中">
      <p>文档 <span class="sm-mono">{{ result.document_id }}</span> · 版本 <span class="sm-mono">{{ result.version_id }}</span></p>
      <p>解析状态：{{ result.parse_status }}，完成后可在文档列表中查看。</p>
    </ElAlert>

    <ElForm v-else label-position="top">
      <ElFormItem label="知识库" required>
        <ElSelect v-model="knowledgeBaseId" style="width: 100%">
          <ElOption v-for="kb in knowledgeBases" :key="kb.id" :label="`${kb.name}（${kb.locale}/${kb.region}）`" :value="kb.id" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="文档标题" required>
        <ElInput v-model="title" maxlength="240" placeholder="例如：退换货政策（2026 版）" />
      </ElFormItem>
      <ElFormItem label="文档类型" required>
        <ElSelect v-model="docType" style="width: 100%">
          <ElOption v-for="option in docTypeOptions" :key="option" :label="docTypeLabel(option)" :value="option" />
        </ElSelect>
      </ElFormItem>
      <div class="sm-row sm-form-row">
        <ElFormItem label="语言（BCP 47）" required>
          <ElInput v-model="locale" style="width: 8rem" />
        </ElFormItem>
        <ElFormItem label="地区（ISO 3166-1）" required>
          <ElInput v-model="region" style="width: 8rem" />
        </ElFormItem>
      </div>
      <div class="sm-row sm-form-row">
        <ElFormItem label="生效开始（UTC）" required>
          <ElDatePicker v-model="effectiveFrom" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss.SSS[Z]" style="width: 100%" />
        </ElFormItem>
        <ElFormItem label="生效结束（UTC，可空）">
          <ElDatePicker v-model="effectiveTo" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss.SSS[Z]" style="width: 100%" />
        </ElFormItem>
      </div>
      <ElFormItem label="文件（≤ 20 MiB，PDF/DOCX/PPTX/MD/TXT）" required>
        <ElUpload
          drag
          :auto-upload="false"
          :limit="1"
          :accept="ACCEPT"
          :on-change="onFileChange"
          :on-remove="() => (file = null)"
        >
          <p v-if="!file">点击或拖拽文件到此处</p>
          <p v-else class="sm-mono">{{ file.name }}</p>
        </ElUpload>
        <p v-if="fileError" class="sm-file-error">{{ fileError }}</p>
      </ElFormItem>
      <ElAlert v-if="error" type="error" :closable="false" show-icon :title="error.message" />
    </ElForm>

    <template #footer>
      <ElButton @click="close">{{ result ? '关闭' : '取消' }}</ElButton>
      <ElButton v-if="!result" type="primary" :loading="submitting" :disabled="!canSubmit" @click="onSubmit">
        上传并创建版本
      </ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
.sm-form-row {
  gap: 12px;
  align-items: flex-start;
}

.sm-form-row > * {
  flex: 1;
}

.sm-file-error {
  margin: 4px 0 0;
  color: var(--sm-danger);
  font-size: 12px;
}
</style>
