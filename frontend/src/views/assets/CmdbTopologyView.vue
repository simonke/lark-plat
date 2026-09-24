<template>
  <div class="page">
    <el-card>
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="实体类型">
          <el-select v-model="q.entity_type" style="width: 130px">
            <el-option v-for="t in ENTITY_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="实体 ID">
          <el-input v-model.number="q.entity_id" style="width: 120px" @keyup.enter="runTopology" />
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="q.direction" style="width: 110px">
            <el-option label="双向" value="both" />
            <el-option label="上游" value="up" />
            <el-option label="下游" value="down" />
          </el-select>
        </el-form-item>
        <el-form-item label="深度">
          <el-input-number v-model="q.depth" :min="0" :max="3" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="runTopology">查询拓扑</el-button>
          <el-button :loading="impactLoading" @click="runImpact">影响分析</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="block">
      <template #header>
        <div class="card-head">
          <span>拓扑</span>
          <el-tag v-if="topo?.truncated" type="warning" size="small">结果已截断（truncated）</el-tag>
        </div>
      </template>
      <el-table :data="topo?.nodes ?? []" border size="small">
        <el-table-column label="节点" min-width="200">
          <template #default="{ row }">{{ nodeLabel(row) }}</template>
        </el-table-column>
        <el-table-column prop="role" label="角色" width="100" />
      </el-table>
      <el-divider content-position="left">边 ({{ topo?.edges?.length ?? 0 }})</el-divider>
      <el-table :data="topo?.edges ?? []" border size="small">
        <el-table-column label="源" min-width="180">
          <template #default="{ row }">{{ nodeLabel(row.src) }}</template>
        </el-table-column>
        <el-table-column label="关系" width="140">
          <template #default="{ row }">{{ relLabel(row.rel_type) }}</template>
        </el-table-column>
        <el-table-column label="目标" min-width="180">
          <template #default="{ row }">{{ nodeLabel(row.dst) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="block">
      <template #header>
        <div class="card-head">
          <span>影响分析（下游可达）</span>
          <el-tag v-if="impact" size="small">共 {{ impact.count }}</el-tag>
          <el-tag v-if="impact?.truncated" type="warning" size="small">结果已截断（truncated）</el-tag>
        </div>
      </template>
      <el-table :data="impact?.affected ?? []" border size="small">
        <el-table-column label="受影响实体" min-width="240">
          <template #default="{ row }">{{ nodeLabel(row) }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="impact && impact.affected.length === 0" description="无可达下游实体" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getTopology, getImpact } from '../../api/assets'
import { extractError } from '../../api/http'
import type { Topology, CmdbImpact, RelationEntityType, CmdbRelType } from '../../api/types'

const ENTITY_TYPES: { value: RelationEntityType; label: string }[] = [
  { value: 'host', label: '主机' },
  { value: 'host_group', label: '主机分组' },
]
const REL_LABELS: Record<CmdbRelType, string> = {
  depends_on: '依赖',
  runs_on: '运行于',
  connects_to: '连接',
  member_of: '属于',
  hosts: '承载',
}

const loading = ref(false)
const impactLoading = ref(false)
const topo = ref<Topology | null>(null)
const impact = ref<CmdbImpact | null>(null)

const q = reactive({
  entity_type: 'host' as RelationEntityType,
  entity_id: undefined as number | undefined,
  direction: 'both' as 'up' | 'down' | 'both',
  depth: 2,
})

function nodeLabel(n: { type?: string; id?: number; label?: string }) {
  if (n.label) return n.label
  const t = n.type === 'host' ? '主机' : '分组'
  return `${t} #${n.id}`
}
function relLabel(rel: string) {
  return REL_LABELS[rel as CmdbRelType] ?? rel
}

function ensureTarget(): boolean {
  if (!q.entity_id) {
    ElMessage.warning('请填写实体 ID')
    return false
  }
  return true
}

async function runTopology() {
  if (!ensureTarget()) return
  loading.value = true
  try {
    topo.value = await getTopology({
      entity_type: q.entity_type,
      entity_id: q.entity_id!,
      direction: q.direction,
      depth: q.depth,
    })
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function runImpact() {
  if (!ensureTarget()) return
  impactLoading.value = true
  try {
    impact.value = await getImpact({
      entity_type: q.entity_type,
      entity_id: q.entity_id!,
      direction: 'down',
      depth: q.depth,
    })
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    impactLoading.value = false
  }
}
</script>

<style scoped>
.block {
  margin-top: 16px;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}
</style>
