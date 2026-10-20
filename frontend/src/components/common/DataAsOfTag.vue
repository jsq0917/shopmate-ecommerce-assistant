<script setup lang="ts">
/**
 * 数据更新时间标签。所有结构化事实必须带 as_of（业务铁律 1）。
 */

import { formatDateTime } from '@/utils/format'

defineProps<{
  asOf?: string | null
  label?: string
}>()
</script>

<template>
  <span class="sm-as-of" :title="asOf ? `数据时间：${formatDateTime(asOf)}` : undefined">
    {{ label ?? '数据更新时间' }}：{{ asOf ? formatDateTime(asOf) : '未知' }}
  </span>
</template>

<style scoped>
.sm-as-of {
  color: var(--sm-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}
</style>
