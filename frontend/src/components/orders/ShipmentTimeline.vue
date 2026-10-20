<script setup lang="ts">
/**
 * 物流时间线：承运商、脱敏单号、节点与预计/实际送达。不展示完整地址或收件人。
 */

import { ElTimeline, ElTimelineItem } from 'element-plus'

import DataAsOfTag from '@/components/common/DataAsOfTag.vue'
import type { ShipmentData } from '@/api/types'
import { formatDateTime, shipmentStatusLabel } from '@/utils/format'

defineProps<{ shipment: ShipmentData }>()
</script>

<template>
  <div class="sm-shipment">
    <div class="sm-between">
      <div>
        <h4 class="sm-shipment-title">
          物流（{{ shipment.carrier }}）
          <span class="sm-shipment-status">{{ shipmentStatusLabel(shipment.status) }}</span>
        </h4>
        <p class="sm-muted">
          运单号（脱敏）：<span class="sm-mono">{{ shipment.tracking_no_masked }}</span>
          <span v-if="shipment.is_synthetic" class="sm-synthetic-tag">合成数据</span>
        </p>
      </div>
      <DataAsOfTag :as-of="shipment.status_updated_at" label="物流更新时间" />
    </div>

    <p class="sm-muted">
      发货时间：{{ formatDateTime(shipment.shipped_at) }} · 预计送达：{{ formatDateTime(shipment.estimated_delivery_at) }} ·
      实际送达：{{ formatDateTime(shipment.delivered_at) }}
    </p>

    <ElTimeline v-if="shipment.events.length">
      <ElTimelineItem
        v-for="(event, index) in [...shipment.events].reverse()"
        :key="index"
        :timestamp="formatDateTime(event.occurred_at)"
        placement="top"
      >
        <span class="sm-event-status">{{ shipmentStatusLabel(event.status) }}</span>
        {{ event.description }}
      </ElTimelineItem>
    </ElTimeline>
    <p v-else class="sm-muted">暂无物流节点。</p>
  </div>
</template>

<style scoped>
.sm-shipment-title {
  margin: 0 0 4px;
  font-size: 15px;
}

.sm-shipment-status {
  margin-left: 8px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgb(31 122 92 / 12%);
  color: var(--sm-primary-dark);
  font-size: 12px;
}

.sm-synthetic-tag {
  margin-left: 8px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--sm-warning-bg);
  color: var(--sm-warning);
  font-size: 11px;
}

.sm-event-status {
  font-weight: 600;
  margin-right: 6px;
}
</style>
