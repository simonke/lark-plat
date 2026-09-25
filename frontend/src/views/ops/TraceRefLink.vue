<template>
  <div class="trace-ref">
    <div class="row">
      <span class="label">Trace</span>
      <el-tag v-if="traceId" size="small" type="info" class="mono">{{ shortTrace(traceId) }}</el-tag>
      <span v-else class="muted">-</span>
      <el-button v-if="traceId" link size="small" @click="copy">复制</el-button>
    </div>
    <div v-if="refEntries.length" class="row refs">
      <span class="label">依据</span>
      <el-tag v-for="[k, v] in refEntries" :key="k" size="small" class="ref-tag">
        {{ k }}: {{ formatRef(v) }}
      </el-tag>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { shortTrace } from '../ai/helpers'

const props = defineProps<{
  traceId?: string | null
  refs?: Record<string, unknown> | null
}>()

const traceId = computed(() => props.traceId ?? '')
const refEntries = computed(() => Object.entries(props.refs ?? {}))

function formatRef(v: unknown): string {
  if (v === null || v === undefined) return '-'
  if (Array.isArray(v)) return v.join(', ')
  return String(v)
}

async function copy() {
  if (!traceId.value) return
  try {
    await navigator.clipboard.writeText(traceId.value)
    ElMessage.success('已复制 trace_id')
  } catch {
    ElMessage.warning('复制失败，请手动选择')
  }
}
</script>

<style scoped>
.trace-ref {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.label {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.mono {
  font-family: var(--el-font-family-mono, monospace);
}
.muted {
  color: var(--el-text-color-placeholder);
}
.refs {
  align-items: flex-start;
}
</style>
