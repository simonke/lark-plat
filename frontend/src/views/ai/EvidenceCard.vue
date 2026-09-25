<template>
  <el-card class="evidence-card" shadow="never">
    <template #header>
      <div class="head">
        <span class="title">{{ title }}</span>
        <div class="badges">
          <el-tag v-if="hitl" size="small" type="warning" effect="plain">HITL · 人工确认</el-tag>
          <el-tag v-if="!authoritative" size="small" type="info" effect="plain">非权威·建议态</el-tag>
        </div>
      </div>
    </template>
    <div class="body">
      <slot />
    </div>
    <div class="foot">
      <span>模型：{{ modelName || '-' }}{{ modelVersion ? ` / ${modelVersion}` : '' }}</span>
      <span>置信度：{{ confidencePercent(confidence) }}</span>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { confidencePercent } from './helpers'

withDefaults(
  defineProps<{
    title: string
    modelName?: string | null
    modelVersion?: string | null
    confidence?: number | null
    authoritative?: boolean
    hitl?: boolean
  }>(),
  { modelName: '', modelVersion: '', confidence: null, authoritative: false, hitl: true },
)
</script>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.title {
  font-weight: 600;
}
.badges {
  display: flex;
  gap: 6px;
}
.body {
  min-height: 24px;
}
.foot {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
