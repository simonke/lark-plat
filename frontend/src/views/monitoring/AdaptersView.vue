<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">采集适配器</span>
          <el-button type="primary" @click="loadStatus">刷新状态</el-button>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="适配器将外部异构监控（Prometheus/ELK/SkyWalking）与自采集 Agent 归一化为标准 MonEvent 事件，来源不排他，规则引擎统一消费。"
        class="hint"
      />

      <el-table :data="adapters" v-loading="loading" border>
        <el-table-column prop="name" label="适配器" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="adapter-name">
              <el-icon :size="18" :style="{ color: adapterColor(row.type) }"><Grid /></el-icon>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="130">
          <template #default="{ row }">{{ adapterLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-tag :type="row.enabled === 1 ? 'success' : 'info'" size="small">
              {{ row.enabled === 1 ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="metrics_received_count" label="指标数" width="90" />
        <el-table-column label="最近心跳" min-width="160">
          <template #default="{ row }">{{ formatTime(row.last_heartbeat) }}</template>
        </el-table-column>
        <el-table-column label="错误" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.error_msg || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="warning"
              :loading="testing === row.id"
              v-perm="'monitor:rule:test'"
              @click="onTest(row.id)"
            >
              测试连通
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Grid } from '@element-plus/icons-vue'
import { getAdapters, testAdapter } from '../../api/monitoring'
import type { MonAdapterOut } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const testing = ref<number | null>(null)
const adapters = ref<MonAdapterOut[]>([])

const ADAPTER_MAP: Record<string, string> = {
  agent: 'Agent 自采集',
  prometheus: 'Prometheus',
  alertmanager: 'Alertmanager',
  elk: 'ELK',
  skywalking: 'SkyWalking',
  webhook: 'Webhook',
}

function adapterLabel(type: string): string {
  return ADAPTER_MAP[type] ?? type
}
function adapterColor(type: string): string {
  const map: Record<string, string> = {
    agent: '#409eff',
    prometheus: '#e6a23c',
    alertmanager: '#f56c6c',
    elk: '#67c23a',
    skywalking: '#f56c6c',
    webhook: '#909399',
  }
  return map[type] ?? '#909399'
}
const STATUS_MAP: Record<string, string> = {
  healthy: '正常',
  degraded: '降级',
  disabled: '停用',
  error: '异常',
  unknown: '未知',
}
function statusLabel(st: string): string {
  return STATUS_MAP[st] ?? st
}
function statusTag(st: string): string {
  const map: Record<string, string> = {
    healthy: 'success',
    degraded: 'warning',
    disabled: 'info',
    error: 'danger',
    unknown: 'info',
  }
  return map[st] ?? 'info'
}
function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

async function loadStatus() {
  loading.value = true
  try {
    const page = await getAdapters({ page: 1, size: 100 })
    adapters.value = page.list
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function onTest(id: number) {
  testing.value = id
  try {
    const result = await testAdapter(id)
    if (result.ok) {
      ElMessage.success(`${result.error_message ?? '连通正常'}`)
    } else {
      ElMessage.error(`连通失败：${result.error_message ?? '未知原因'}`)
    }
    loadStatus()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    testing.value = null
  }
}

onMounted(loadStatus)
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
  margin-bottom: 16px;
}
.adapter-name {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
