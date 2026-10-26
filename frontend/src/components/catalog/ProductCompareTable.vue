<script setup lang="ts">
/**
 * 商品比较表。缺失字段由后端标记 known=false / display=unknown，
 * 前端只展示，不推断、不补写（PRD F-09 / ERR-12）。
 */

import DataAsOfTag from '@/components/common/DataAsOfTag.vue'
import type { CompareData } from '@/api/types'

defineProps<{ data: CompareData }>()

/** 合并商品名与规格名，避免重复（variant_title 常自带 product title 前缀）。 */
function displayTitle(product: { title: string; variant_title: string | null }): string {
  const vt = product.variant_title?.trim()
  if (!vt) return product.title
  if (vt === product.title) return product.title
  // variant_title 以 product.title 开头（如 "速派 L 20W 数据线 · 云雾白"）则不重复拼
  if (vt.startsWith(product.title)) return vt
  return `${product.title} · ${vt}`
}
</script>

<template>
  <div class="sm-compare">
    <div class="sm-between">
      <h3 class="sm-compare-title">商品比较（{{ data.products.length }} 件）</h3>
      <DataAsOfTag :as-of="data.as_of" />
    </div>
    <div class="sm-compare-scroll">
      <table class="sm-compare-table">
        <thead>
          <tr>
            <th class="sm-compare-rowhead">对比项</th>
            <th v-for="product in data.products" :key="product.product_id">
              <span class="sm-compare-product">
                {{ displayTitle(product) }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in data.rows" :key="row.key">
            <th class="sm-compare-rowhead">{{ row.label }}</th>
            <td
              v-for="value in row.values"
              :key="value.product_id"
              :class="{ 'sm-compare-unknown': !value.known }"
            >
              {{ value.display || 'unknown' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="sm-muted">unknown 表示数据库中没有该字段，系统不会推测数值。</p>
  </div>
</template>

<style scoped>
.sm-compare {
  margin: 8px 0;
}

.sm-compare-title {
  margin: 0;
  font-size: 15px;
}

.sm-compare-scroll {
  overflow-x: auto;
  margin-top: 8px;
}

.sm-compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.sm-compare-table th,
.sm-compare-table td {
  border: 1px solid var(--sm-border);
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}

.sm-compare-table thead th {
  background: var(--sm-bg);
}

.sm-compare-rowhead {
  width: 110px;
  color: var(--sm-text-secondary);
  font-weight: 600;
}

.sm-compare-product {
  font-weight: 700;
}

.sm-compare-unknown {
  color: var(--sm-text-secondary);
}
</style>
