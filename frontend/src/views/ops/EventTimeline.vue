<template>
  <el-timeline v-if="events.length" class="event-timeline">
    <el-timeline-item
      v-for="e in events"
      :key="e.id"
      :timestamp="formatTime(e.ts || e.created_at)"
      placement="top"
      :type="sourceTag(e.source)"
    >
      <div class="event-line">
        <el-tag size="small" :type="sourceTag(e.source)">{{ sourceLabel(e.source) }}</el-tag>
        <span class="action">{{ e.action }}</span>
        <span class="entity">{{ e.entity_type }}#{{ e.entity_id }}</span>
        <el-tag v-if="e.result" size="small" effect="plain" :type="resultTag(e.result)">{{ e.result }}</el-tag>
      </div>
      <div v-if="e.trace_id" class="trace">trace: {{ shortTrace(e.trace_id) }}</div>
    </el-timeline-item>
  </el-timeline>
  <el-empty v-else description="暂无事件" />
</template>

<script setup lang="ts">
import type { OpsEvent } from '../../api/types'
import { sourceLabel, sourceTag, shortTrace } from '../ai/helpers'

defineProps<{ events: OpsEvent[] }>()

function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

function resultTag(result: string): string {
  const r = result.toLowerCase()
  if (r.includes('fail') || r.includes('error') || r.includes('reject')) return 'danger'
  if (r.includes('success') || r.includes('ok') || r.includes('done')) return 'success'
  return 'info'
}
</script>

<style scoped>
.event-timeline {
  padding-left: 4px;
}
.event-line {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.action {
  font-weight: 600;
}
.entity {
  color: var(--el-text-color-secondary);
}
.trace {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  font-family: var(--el-font-family-mono, monospace);
}
</style>
