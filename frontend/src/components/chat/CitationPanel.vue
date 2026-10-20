<script setup lang="ts">
/**
 * 政策引用面板（引用侧栏内容）。字段与 docs/06-api.md 7.6 / 业务铁律 3 对齐：
 * 文档、章节/页码、版本、生效日期、片段预览与 as_of。excerpt 只作为纯文本展示。
 */

import DataAsOfTag from '@/components/common/DataAsOfTag.vue'
import { formatDate } from '@/utils/format'
import type { MessageCitation } from '@/api/types'

defineProps<{ citations: MessageCitation[] }>()

function effectiveText(from: string | null, to: string | null): string {
  if (!from && !to) return '生效期未知'
  if (from && to) return `${formatDate(from)} 至 ${formatDate(to)}`
  if (from) return `${formatDate(from)} 起长期有效`
  return `截至 ${formatDate(to)}`
}
</script>

<template>
  <div class="sm-citation-panel">
    <p v-if="!citations.length" class="sm-muted">本轮回答没有可展示的引用。</p>
    <article v-for="citation in citations" :key="citation.citation_id" class="sm-citation">
      <header class="sm-citation-head">
        <span v-if="citation.label" class="sm-citation-label">{{ citation.label }}</span>
        <h4 class="sm-citation-title">{{ citation.title }}</h4>
      </header>
      <p class="sm-citation-meta">
        <span v-if="citation.heading">章节：{{ citation.heading }}</span>
        <span v-if="citation.page_no !== null"> · 第 {{ citation.page_no }} 页</span>
        <span> · 版本 {{ citation.version }}</span>
        <span> · {{ effectiveText(citation.effective_from, citation.effective_to) }}</span>
      </p>
      <p v-if="citation.excerpt" class="sm-citation-excerpt">{{ citation.excerpt }}</p>
      <DataAsOfTag :as-of="citation.as_of" label="检索时间" />
    </article>
  </div>
</template>

<style scoped>
.sm-citation-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sm-citation {
  border: 1px solid var(--sm-border);
  border-radius: var(--sm-radius);
  padding: 10px 12px;
  background: var(--sm-surface);
}

.sm-citation-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sm-citation-label {
  flex: none;
  min-width: 24px;
  text-align: center;
  padding: 0 6px;
  border-radius: 6px;
  background: rgb(31 122 92 / 12%);
  color: var(--sm-primary-dark);
  font-size: 12px;
  font-weight: 700;
}

.sm-citation-title {
  margin: 0;
  font-size: 14px;
}

.sm-citation-meta {
  margin: 4px 0;
  font-size: 12px;
  color: var(--sm-text-secondary);
}

.sm-citation-excerpt {
  margin: 4px 0;
  font-size: 13px;
  white-space: pre-wrap;
}
</style>
