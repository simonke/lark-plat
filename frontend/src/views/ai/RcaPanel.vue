<template>
  <div class="rca" v-loading="loading">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="AI 根因候选为非权威建议，需人工研判，不会自动处置"
    />
    <template v-if="report">
      <div class="meta">
        <span class="label">根实体</span>
        <span>{{ rootEntityLabel(report.root_entity) }}</span>
        <el-tag size="small" effect="plain" class="tag">depth {{ report.depth }}</el-tag>
        <el-tag size="small" type="info" effect="plain" class="tag">仅建议</el-tag>
      </div>

      <el-table :data="report.candidates" size="small" border class="cands">
        <el-table-column label="候选实体" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.entity_type }}#{{ row.entity_id }}</template>
        </el-table-column>
        <el-table-column label="评分" width="90">
          <template #default="{ row }">{{ row.score.toFixed(2) }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="依据" min-width="200" show-overflow-tooltip />
        <el-table-column label="证据" width="80">
          <template #default="{ row }">{{ (row.evidence ?? []).length }}</template>
        </el-table-column>
      </el-table>

      <el-empty v-if="report.candidates.length === 0" description="未发现下游根因候选（空集）" />
    </template>
    <el-empty v-else-if="!loading" description="尚未生成根因候选" />
  </div>
</template>

<script setup lang="ts">
import type { RcaReport } from '../../api/types'
import { rootEntityLabel } from './helpers'

defineProps<{
  report: RcaReport | null
  loading?: boolean
}>()
</script>

<style scoped>
.rca {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
.meta .label {
  color: var(--el-text-color-secondary);
}
.tag {
  margin-left: 4px;
}
.cands {
  margin-top: 4px;
}
</style>
