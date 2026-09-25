<template>
  <el-descriptions :column="1" border size="small">
    <el-descriptions-item label="实体类型">{{ entityType || '-' }}</el-descriptions-item>
    <el-descriptions-item label="实体 ID">
      <span class="mono">{{ entityId || '-' }}</span>
    </el-descriptions-item>
    <el-descriptions-item label="事件数">{{ eventCount }}</el-descriptions-item>
  </el-descriptions>
</template>

<script setup lang="ts">
defineProps<{
  entityType?: string
  entityId?: string
  eventCount?: number
}>()
</script>

<style scoped>
.mono {
  font-family: var(--el-font-family-mono, monospace);
}
</style>
