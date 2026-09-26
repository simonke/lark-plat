<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">告警聚合（AI 降噪）</span>
          <el-tag size="small" type="info" effect="plain">AI 输出非权威·仅供参考</el-tag>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load">
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="待评估" value="pending" />
            <el-option label="触发中" value="firing" />
            <el-option label="已确认" value="acknowledged" />
            <el-option label="已解决" value="resolved" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="query.severity" clearable placeholder="全部" style="width: 120px">
            <el-option label="严重" value="critical" />
            <el-option label="警告" value="warning" />
            <el-option label="信息" value="info" />
          </el-select>
        </el-form-item>
        <el-form-item label="根因深度">
          <el-input-number v-model="depth" :min="RCA_DEPTH_MIN" :max="RCA_DEPTH_MAX" controls-position="right" style="width: 120px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-alert
        v-if="disabled"
        type="warning"
        :closable="false"
        show-icon
        title="AI 告警聚合未启用（flag ai.rca 关闭）"
        class="hint"
      />

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column label="实体类型" width="120">
          <template #default="{ row }">{{ row.entity_type ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="entity_id" label="实体" min-width="160" show-overflow-tooltip />
        <el-table-column label="规则" width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.rule ? row.rule : '—' }}</template>
        </el-table-column>
        <el-table-column label="告警数" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ row.count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最高级别" width="100">
          <template #default="{ row }">
            <el-tag :type="severityTag(row.max_severity)" size="small">{{ severityLabel(row.max_severity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近告警" width="100">
          <template #default="{ row }">{{ (row.alert_ids ?? [])[0] ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="!(row.alert_ids ?? []).length"
              @click="onRca(row)"
            >
              根因分析
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next, sizes"
        :total="total"
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :page-sizes="[10, 20, 50]"
        @change="load"
      />
    </el-card>

    <el-dialog v-model="rcaVisible" title="AI 根因候选" width="720px">
      <div v-if="rcaAlertId !== null" class="rca-sub">告警 #{{ rcaAlertId }}</div>
      <RcaPanel :report="report" :loading="rcaLoading" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { aggregateAlerts, alertRca } from '../../api/ai'
import { extractError } from '../../api/http'
import type { AlertAggregateItem, AlertAggregateQuery, RcaReport } from '../../api/types'
import {
  RCA_DEPTH_DEFAULT,
  RCA_DEPTH_MAX,
  RCA_DEPTH_MIN,
  normalizeRcaDepth,
  severityLabel,
  severityTag,
} from '../ai/helpers'
import RcaPanel from '../ai/RcaPanel.vue'

const loading = ref(false)
const disabled = ref(false)
const rows = ref<AlertAggregateItem[]>([])
const total = ref(0)
const query = reactive<AlertAggregateQuery>({ page: 1, size: 10 })
const depth = ref(RCA_DEPTH_DEFAULT)

const rcaVisible = ref(false)
const rcaLoading = ref(false)
const rcaAlertId = ref<number | null>(null)
const report = ref<RcaReport | null>(null)

async function load() {
  loading.value = true
  try {
    const res = await aggregateAlerts({
      status: query.status,
      severity: query.severity,
      page: query.page,
      size: query.size,
    })
    rows.value = res.list
    total.value = res.total
    disabled.value = false
  } catch (e) {
    rows.value = []
    total.value = 0
    disabled.value = true
    ElMessage.warning(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.status = undefined
  query.severity = undefined
  query.page = 1
  load()
}

async function onRca(row: AlertAggregateItem) {
  const alertId = (row.alert_ids ?? [])[0]
  if (!alertId) return
  rcaAlertId.value = alertId
  report.value = null
  rcaVisible.value = true
  rcaLoading.value = true
  try {
    report.value = await alertRca(alertId, normalizeRcaDepth(depth.value))
  } catch (e) {
    ElMessage.warning(extractError(e))
  } finally {
    rcaLoading.value = false
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
.hint {
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.rca-sub {
  margin-bottom: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
