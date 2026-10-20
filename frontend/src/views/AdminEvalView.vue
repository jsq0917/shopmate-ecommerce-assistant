<script setup lang="ts">
/**
 * 评测与模型：触发受控评测（202 + eval_run_id）、查看历史指标与失败配置、
 * 查看模型 profile（不返回密钥）。
 */

import { onMounted, reactive, ref } from 'vue'
import { ElAlert, ElButton, ElCollapse, ElCollapseItem, ElForm, ElFormItem, ElInput, ElTable, ElTableColumn, ElTag } from 'element-plus'

import StateBlock from '@/components/common/StateBlock.vue'
import { adminApi } from '@/api/endpoints'
import { toApiError } from '@/api/errors'
import type { ApiError } from '@/api/errors'
import type { EvalRunItem, ModelProfileItem } from '@/api/types'
import { formatDateTime } from '@/utils/format'

const loading = ref(true)
const error = ref<ApiError | null>(null)
const runs = ref<EvalRunItem[]>([])
const profiles = ref<ModelProfileItem[]>([])
const triggerError = ref<ApiError | null>(null)
const triggerNotice = ref('')
const triggering = ref(false)

const form = reactive({
  datasetName: 'shopmate-core',
  datasetVersion: 'v1',
  seed: '42',
})

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    const [runsData, profilesData] = await Promise.all([adminApi.evalRuns(), adminApi.modelProfiles()])
    runs.value = runsData.items
    profiles.value = profilesData.items
  } catch (caught) {
    error.value = toApiError(caught)
  } finally {
    loading.value = false
  }
}

async function trigger(): Promise<void> {
  triggering.value = true
  triggerError.value = null
  triggerNotice.value = ''
  try {
    const seed = Number(form.seed)
    const data = await adminApi.createEvalRun({
      dataset_name: form.datasetName.trim(),
      dataset_version: form.datasetVersion.trim(),
      seed: Number.isFinite(seed) && form.seed.trim() !== '' ? seed : null,
    })
    triggerNotice.value = `已创建评测任务 ${data.eval_run_id}（queued），结果将在下方列表中更新。`
    await load()
  } catch (caught) {
    triggerError.value = toApiError(caught)
  } finally {
    triggering.value = false
  }
}

function statusType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === 'completed' || status === 'succeeded') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'info'
}

onMounted(load)
</script>

<template>
  <div class="sm-page">
    <h2 class="sm-page-title">评测与模型</h2>
    <p class="sm-muted">评测使用固定数据集与随机种子；指标以实际运行结果为准，不做外推。</p>

    <div class="sm-card">
      <h3 class="sm-section-title">触发评测</h3>
      <ElForm inline @submit.prevent="trigger">
        <ElFormItem label="数据集">
          <ElInput v-model="form.datasetName" style="width: 12rem" />
        </ElFormItem>
        <ElFormItem label="版本">
          <ElInput v-model="form.datasetVersion" style="width: 7rem" />
        </ElFormItem>
        <ElFormItem label="随机种子">
          <ElInput v-model="form.seed" style="width: 7rem" placeholder="42" />
        </ElFormItem>
        <ElFormItem>
          <ElButton type="primary" :loading="triggering" @click="trigger">运行评测</ElButton>
        </ElFormItem>
      </ElForm>
      <ElAlert v-if="triggerNotice" type="success" :closable="false" show-icon :title="triggerNotice" />
      <ElAlert v-if="triggerError" type="error" :closable="false" show-icon :title="triggerError.message" />
    </div>

    <div class="sm-card">
      <h3 class="sm-section-title">评测历史</h3>
      <StateBlock
        :loading="loading && !runs.length"
        :error="error"
        :empty="!loading && !error && runs.length === 0"
        empty-text="暂无评测记录。"
        @retry="load"
      >
        <ElTable :data="runs" size="small" border>
          <ElTableColumn label="任务 ID" min-width="210">
            <template #default="{ row }"><span class="sm-mono">{{ row.eval_run_id }}</span></template>
          </ElTableColumn>
          <ElTableColumn label="数据集" min-width="160">
            <template #default="{ row }">{{ row.dataset_name }}@{{ row.dataset_version }}</template>
          </ElTableColumn>
          <ElTableColumn label="状态" min-width="100">
            <template #default="{ row }">
              <ElTag size="small" :type="statusType(row.status)">{{ row.status }}</ElTag>
            </template>
          </ElTableColumn>
          <ElTableColumn label="创建时间" min-width="150">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </ElTableColumn>
          <ElTableColumn label="指标" min-width="260">
            <template #default="{ row }">
              <ElCollapse v-if="Object.keys(row.metrics).length">
                <ElCollapseItem title="查看指标 JSON">
                  <pre class="sm-metrics">{{ JSON.stringify(row.metrics, null, 2) }}</pre>
                </ElCollapseItem>
              </ElCollapse>
              <span v-else class="sm-muted">--</span>
            </template>
          </ElTableColumn>
        </ElTable>
      </StateBlock>
    </div>

    <div class="sm-card">
      <h3 class="sm-section-title">模型 Profile（不含密钥）</h3>
      <ElTable :data="profiles" size="small" border>
        <ElTableColumn prop="profile_id" label="Profile" min-width="140" />
        <ElTableColumn prop="model_name" label="模型" min-width="160" />
        <ElTableColumn prop="provider" label="提供方" min-width="160" />
        <ElTableColumn label="结构化工具" min-width="120">
          <template #default="{ row }">{{ row.supports_structured_tools ? '支持' : '不支持' }}</template>
        </ElTableColumn>
      </ElTable>
    </div>
  </div>
</template>

<style scoped>
.sm-page-title {
  margin: 0 0 4px;
  font-size: 18px;
}

.sm-card {
  margin-bottom: 12px;
}

.sm-section-title {
  margin: 0 0 10px;
  font-size: 15px;
}

.sm-metrics {
  margin: 0;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
