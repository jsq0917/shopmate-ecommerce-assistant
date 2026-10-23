<script setup lang="ts">
/**
 * 会话级推理参数面板（课程任务书硬性要求：温度、topP、最长输出 token 数、历史对话轮数
 * 均可从对话页配置）。
 *
 * 语义（与后端一致）：
 * - 四个参数都保存在**会话**上（stage 19），刷新不丢、换会话跟着走；
 * - 未设置 = 不覆盖，用服务端默认值（GET /generation-defaults，经 defaults 传入）；
 * - 「恢复默认」把所有字段显式置空，等价于恢复服务端默认；
 * - 参数只影响后续轮次：已生成的历史消息不会被改写。
 *
 * 组件完全受控：控件值 = 覆盖值 ?? 服务端默认；每次拖动/输入实时向上发
 * update:modelValue（父级更新草稿，滑块拇指才能跟上），在松手/失焦等提交点发一次
 * change（父级才 PATCH）。max_tokens 的上限取 defaults.max_tokens_cap，与后端一致。
 */

import { computed } from 'vue'
import { ElButton, ElInputNumber, ElSlider } from 'element-plus'

import type { ConversationGenerationParams, GenerationDefaults } from '@/api/types'

const props = defineProps<{
  modelValue: ConversationGenerationParams
  /** 服务端默认值；null = 仍在加载（面板禁用）。 */
  defaults: GenerationDefaults | null
  disabled?: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: ConversationGenerationParams): void
  (e: 'change', value: ConversationGenerationParams): void
}>()

/** 全部置空的参数 = 恢复默认。 */
const EMPTY: ConversationGenerationParams = {
  temperature: null,
  top_p: null,
  max_tokens: null,
  history_turns: null,
}

const ready = computed(() => props.defaults !== null)
const controlsDisabled = computed(() => props.disabled || props.loading || !ready.value)

/** 归一化后的覆盖值：缺省键按「未覆盖」处理。 */
const stored = computed<Required<ConversationGenerationParams>>(() => ({
  temperature: props.modelValue.temperature ?? null,
  top_p: props.modelValue.top_p ?? null,
  max_tokens: props.modelValue.max_tokens ?? null,
  history_turns: props.modelValue.history_turns ?? null,
}))

const effectiveTemperature = computed(
  () => stored.value.temperature ?? props.defaults?.temperature ?? 0,
)
const effectiveTopP = computed(() => stored.value.top_p ?? props.defaults?.top_p ?? null)
const effectiveMaxTokens = computed(() => stored.value.max_tokens ?? props.defaults?.max_tokens ?? null)
const effectiveHistoryTurns = computed(
  () => stored.value.history_turns ?? props.defaults?.history_turns ?? 0,
)

const maxTokensCap = computed(() => props.defaults?.max_tokens_cap ?? 4096)

/** 控件绑定值：覆盖值优先，否则停在与默认值等价的位置。 */
const temperatureValue = computed(() => effectiveTemperature.value)
const topPValue = computed(() => effectiveTopP.value ?? 1)
const maxTokensValue = computed(() => effectiveMaxTokens.value ?? 1024)
const historyTurnsValue = computed(() => effectiveHistoryTurns.value)

function commit(field: keyof ConversationGenerationParams, value: number): void {
  emit('change', { ...props.modelValue, [field]: value })
}

/** ElSlider 开启范围选择时会传数组，本项目不启用，取首值即可。 */
function scalar(value: number | number[]): number | null {
  const next = Array.isArray(value) ? value[0] : value
  return typeof next === 'number' ? next : null
}

/** 拖动过程中的实时更新：只改父级草稿，不触发 PATCH。 */
function onTemperatureInput(value: number | number[]): void {
  const next = scalar(value)
  if (next !== null) emit('update:modelValue', { ...props.modelValue, temperature: next })
}

function onTemperatureCommit(value: number | number[]): void {
  const next = scalar(value)
  if (next !== null) commit('temperature', next)
}

function onTopPInput(value: number | number[]): void {
  const next = scalar(value)
  if (next !== null) emit('update:modelValue', { ...props.modelValue, top_p: next })
}

function onTopPCommit(value: number | number[]): void {
  const next = scalar(value)
  if (next !== null) commit('top_p', next)
}

function onMaxTokensInput(value: number | undefined): void {
  if (typeof value === 'number') {
    emit('update:modelValue', { ...props.modelValue, max_tokens: value })
  }
}

function onHistoryTurnsInput(value: number | undefined): void {
  if (typeof value === 'number') {
    emit('update:modelValue', { ...props.modelValue, history_turns: value })
  }
}

function resetToDefaults(): void {
  emit('change', { ...EMPTY })
}

const effectiveText = computed(() => {
  if (!props.defaults) return '默认值暂不可用，参数面板已禁用'
  const topP = effectiveTopP.value
  const maxTokens = effectiveMaxTokens.value
  return [
    `温度 ${effectiveTemperature.value}`,
    `top_p ${topP === null ? '默认（不限）' : topP}`,
    `最长输出 ${maxTokens === null ? '默认（不限）' : `${maxTokens} tokens`}`,
    `历史 ${effectiveHistoryTurns.value} 轮`,
  ].join(' · ')
})

const hasOverride = computed(
  () =>
    stored.value.temperature !== null ||
    stored.value.top_p !== null ||
    stored.value.max_tokens !== null ||
    stored.value.history_turns !== null,
)

/** 面板内的说明条：未覆盖时提示默认值来源，避免用户误以为参数没生效。 */
function hintFor(field: keyof ConversationGenerationParams): string {
  if (stored.value[field] !== null && stored.value[field] !== undefined) return '已设置'
  if (!props.defaults) return ''
  switch (field) {
    case 'temperature':
      return `默认 ${props.defaults.temperature}`
    case 'top_p':
      return props.defaults.top_p === null ? '默认不限制' : `默认 ${props.defaults.top_p}`
    case 'max_tokens':
      return props.defaults.max_tokens === null
        ? '默认不限制'
        : `默认 ${props.defaults.max_tokens} tokens`
    case 'history_turns':
      return `默认 ${props.defaults.history_turns} 轮`
    default:
      return ''
  }
}
</script>

<template>
  <div class="sm-gen-panel" data-testid="generation-params-panel">
    <div class="sm-gen-row">
      <span class="sm-gen-label">温度 temperature</span>
      <ElSlider
        class="sm-gen-slider"
        data-testid="gen-temperature"
        :model-value="temperatureValue"
        :min="0"
        :max="1"
        :step="0.05"
        :disabled="controlsDisabled"
        show-input
        :show-input-controls="false"
        input-size="small"
        @update:model-value="onTemperatureInput"
        @change="onTemperatureCommit"
      />
      <span class="sm-gen-hint" :data-testid="`gen-hint-temperature`">{{ hintFor('temperature') }}</span>
    </div>

    <div class="sm-gen-row">
      <span class="sm-gen-label">top_p</span>
      <ElSlider
        class="sm-gen-slider"
        data-testid="gen-top-p"
        :model-value="topPValue"
        :min="0"
        :max="1"
        :step="0.05"
        :disabled="controlsDisabled"
        show-input
        :show-input-controls="false"
        input-size="small"
        @update:model-value="onTopPInput"
        @change="onTopPCommit"
      />
      <span class="sm-gen-hint" :data-testid="`gen-hint-top-p`">{{ hintFor('top_p') }}</span>
    </div>

    <div class="sm-gen-row">
      <span class="sm-gen-label">最长输出 tokens</span>
      <ElInputNumber
        class="sm-gen-number"
        data-testid="gen-max-tokens"
        :model-value="maxTokensValue"
        :min="256"
        :max="maxTokensCap"
        :step="128"
        :disabled="controlsDisabled"
        size="small"
        controls-position="right"
        @update:model-value="onMaxTokensInput"
        @change="(v: number | undefined) => typeof v === 'number' && commit('max_tokens', v)"
      />
      <span class="sm-gen-hint" :data-testid="`gen-hint-max-tokens`">{{ hintFor('max_tokens') }}</span>
    </div>

    <div class="sm-gen-row">
      <span class="sm-gen-label">历史轮数</span>
      <ElInputNumber
        class="sm-gen-number"
        data-testid="gen-history-turns"
        :model-value="historyTurnsValue"
        :min="0"
        :max="10"
        :step="1"
        :disabled="controlsDisabled"
        size="small"
        controls-position="right"
        @update:model-value="onHistoryTurnsInput"
        @change="(v: number | undefined) => typeof v === 'number' && commit('history_turns', v)"
      />
      <span class="sm-gen-hint" :data-testid="`gen-hint-history-turns`">{{
        hintFor('history_turns')
      }}</span>
    </div>

    <p class="sm-gen-effective" data-testid="gen-effective">当前生效：{{ effectiveText }}</p>

    <div class="sm-gen-footer">
      <span class="sm-gen-note">参数随会话保存，只影响后续提问</span>
      <ElButton
        size="small"
        text
        type="primary"
        data-testid="gen-reset"
        :disabled="controlsDisabled || !hasOverride"
        @click="resetToDefaults"
      >
        恢复默认
      </ElButton>
    </div>
  </div>
</template>

<style scoped>
.sm-gen-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: min(26rem, 88vw);
  padding: 4px 2px;
}

/*
 * 两行布局：第一行「标签 + 控件」，第二行右侧显示「已设置 / 默认 x」。
 * Element Plus 的滑块内部固定占用 130px 输入框 + 30px 间距，单行三列会把轨道挤成 0 宽
 * （用户看不到也点不到），所以轨道必须独占一整行。
 */
.sm-gen-row {
  display: grid;
  grid-template-columns: 6.5rem minmax(0, 1fr);
  align-items: center;
  gap: 2px 8px;
}

.sm-gen-label {
  font-size: 12px;
  color: var(--sm-text-secondary, #4b5563);
  white-space: nowrap;
}

.sm-gen-slider {
  min-width: 0;
}

:deep(.el-slider__input) {
  width: 5.5rem;
}

.sm-gen-number {
  width: 7rem;
}

.sm-gen-hint {
  grid-column: 2;
  font-size: 11px;
  color: var(--sm-text-muted, #6b7280);
  white-space: nowrap;
  text-align: right;
}

.sm-gen-effective {
  margin: 2px 0 0;
  padding: 8px 10px;
  border-radius: var(--sm-radius, 10px);
  background: var(--sm-bg, #f6f7fb);
  font-size: 12px;
  color: var(--sm-text-secondary, #4b5563);
}

.sm-gen-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sm-gen-note {
  font-size: 11px;
  color: var(--sm-text-muted, #6b7280);
}
</style>
