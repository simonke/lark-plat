<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">AI 审计（ai_action）</span>
          <el-tag size="small" type="info" effect="plain">append-only</el-tag>
        </div>
      </template>
      <el-form inline @submit.prevent="onSearch">
        <el-form-item label="决策">
          <el-select v-model="query.decision" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="d in AI_ACTION_DECISIONS" :key="d" :label="decisionLabel(d)" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="Trace">
          <el-input v-model="query.trace_id" clearable style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSearch">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border @row-click="open">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="决策" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="decisionTag(row.decision)">{{ decisionLabel(row.decision) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="hasApprovalMode" label="批准方式" width="130">
          <template #default="{ row }">
            <el-tag size="small" :type="approvalModeTag(row.approval_mode)" effect="plain">
              {{ approvalModeLabel(row.approval_mode) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型" width="140" show-overflow-tooltip />
        <el-table-column label="版本" width="120">
          <template #default="{ row }">{{ row.model_version || '-' }}</template>
        </el-table-column>
        <el-table-column label="置信度" width="90">
          <template #default="{ row }">{{ confidencePercent(row.confidence) }}</template>
        </el-table-column>
        <el-table-column prop="actor" label="操作人" width="90" />
        <el-table-column label="Trace" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ shortTrace(row.trace_id) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :page-sizes="[10, 20, 50]"
        @change="load"
      />
    </el-card>

    <el-drawer v-model="detailVisible" title="证据卡" size="440px">
      <EvidenceCard
        v-if="current"
        title="AI 动作证据"
        :model-name="current.model_name"
        :model-version="current.model_version"
        :confidence="current.confidence"
        :authoritative="false"
        :hitl="true"
      >
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="决策">{{ decisionLabel(current.decision) }}</el-descriptions-item>
          <el-descriptions-item label="批准方式">{{ approvalModeLabel(current.approval_mode) }}</el-descriptions-item>
          <el-descriptions-item label="策略引用">{{ current.policy_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item label="验证锚">{{ current.verification_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item label="回滚锚">{{ current.rollback_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item label="依据引用">{{ current.why_ref || '-' }}</el-descriptions-item>
          <el-descriptions-item label="结果">{{ current.result || '-' }}</el-descriptions-item>
          <el-descriptions-item label="操作人">{{ current.actor ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="Trace">{{ current.trace_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="输入快照">
            <pre class="snapshot">{{ JSON.stringify(current.input_snapshot, null, 2) }}</pre>
          </el-descriptions-item>
          <el-descriptions-item label="依据">
            <pre class="snapshot">{{ JSON.stringify(current.basis_refs, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </EvidenceCard>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAiActions } from '../../api/ai'
import { extractError } from '../../api/http'
import type { AiAction, AiActionQuery } from '../../api/types'
import {
  AI_ACTION_DECISIONS,
  decisionLabel,
  decisionTag,
  confidencePercent,
  shortTrace,
  approvalModeLabel,
  approvalModeTag,
} from './helpers'
import EvidenceCard from './EvidenceCard.vue'

const loading = ref(false)
const rows = ref<AiAction[]>([])
const total = ref(0)
const query = reactive<AiActionQuery>({ page: 1, size: 20 })
const detailVisible = ref(false)
const current = ref<AiAction | null>(null)
// P6: the "批准方式" column only appears once `/ai/actions` exposes `approval_mode`.
const hasApprovalMode = computed(() => rows.value.some((r) => r.approval_mode != null))

function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

function onSearch() {
  query.page = 1
  load()
}

function open(row: AiAction) {
  current.value = row
  detailVisible.value = true
}

async function load() {
  loading.value = true
  try {
    const page = await listAiActions({ ...query })
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    rows.value = []
    total.value = 0
    ElMessage.warning(extractError(e))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-weight: 600;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.snapshot {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
}
</style>
