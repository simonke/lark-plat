<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">告警事件</span>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="loadAlerts">
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="待评估" value="pending" />
            <el-option label="触发中" value="firing" />
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
        <el-form-item label="来源">
          <el-select v-model="query.source" clearable placeholder="全部" style="width: 160px">
            <el-option label="Agent 自采集" value="agent" />
            <el-option label="Prometheus" value="prometheus" />
            <el-option label="ELK" value="elk" />
            <el-option label="SkyWalking" value="skywalking" />
          </el-select>
        </el-form-item>
        <el-form-item label="对象">
          <el-input v-model="query.entity_id" clearable placeholder="主机/服务 ID" style="width: 180px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadAlerts">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="alerts" v-loading="loading" border>
        <el-table-column label="级别" width="90">
          <template #default="{ row }">
            <el-tag :type="severityTag(row.severity)" size="small">{{ severityLabel(row.severity) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">
            <span>{{ sourceLabel(row.source) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="entity_name" label="对象" min-width="130" show-overflow-tooltip />
        <el-table-column prop="rule_name" label="规则" min-width="150" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="first_seen_at" label="首次时间" min-width="160" show-overflow-tooltip />
        <el-table-column prop="last_seen_at" label="最近时间" min-width="160" show-overflow-tooltip />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status !== 'resolved'"
              size="small"
              type="warning"
              v-perm="'monitor:alert:resolve'"
              @click="onResolve(row)"
            >
              解决
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
        @change="loadAlerts"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listAlertEvents, resolveAlert } from '../../api/monitoring'
import type { MonAlertEventOut, MonAlertEventQuery } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const alerts = ref<MonAlertEventOut[]>([])
const total = ref(0)
const query = reactive<MonAlertEventQuery>({ page: 1, size: 10 })

const SOURCE_MAP: Record<string, string> = {
  agent: 'Agent',
  prometheus: 'Prometheus',
  elk: 'ELK',
  skywalking: 'SkyWalking',
}
const SEVERITY_MAP: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '信息',
}
const STATUS_MAP: Record<string, string> = {
  pending: '待评估',
  firing: '触发中',
  resolved: '已解决',
}

function sourceLabel(src: string): string {
  return SOURCE_MAP[src] ?? src
}
function severityLabel(sev: string): string {
  return SEVERITY_MAP[sev] ?? sev
}
function severityTag(sev: string): string {
  const map: Record<string, string> = { critical: 'danger', warning: 'warning', info: 'info' }
  return map[sev] ?? 'info'
}
function statusLabel(st: string): string {
  return STATUS_MAP[st] ?? st
}
function statusTag(st: string): string {
  const map: Record<string, string> = { pending: 'info', firing: 'danger', resolved: 'success' }
  return map[st] ?? 'info'
}

async function loadAlerts() {
  loading.value = true
  try {
    const page = await listAlertEvents(query)
    alerts.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.status = undefined
  query.severity = undefined
  query.source = undefined
  query.entity_id = undefined
  query.page = 1
  loadAlerts()
}

async function onResolve(row: MonAlertEventOut) {
  try {
    await resolveAlert(row.id)
    ElMessage.success('已解决')
    loadAlerts()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(loadAlerts)
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
</style>
