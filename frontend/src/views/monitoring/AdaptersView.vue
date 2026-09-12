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
        <el-table-column label="适配器" width="180">
          <template #default="{ row }">
            <div class="adapter-name">
              <el-icon :size="18" :style="{ color: adapterColor(row.type) }"><Grid /></el-icon>
              <span>{{ adapterLabel(row.type) }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="130" />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="连通" width="90">
          <template #default="{ row }">
            <el-tag :type="row.connected ? 'success' : 'danger'" size="small">
              {{ row.connected ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip />
        <el-table-column prop="last_check_at" label="最近检查" min-width="160">
          <template #default="{ row }">
            {{ formatTime(row.last_check_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              type="warning"
              :loading="testing === row.type"
              v-perm="'monitor:rule:test'"
              @click="onTest(row.type)"
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
import { listAdapterStatus, testAdapter } from '../../api/monitoring'
import type { AdapterStatus } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const testing = ref<string | null>(null)
const adapters = ref<AdapterStatus[]>([])

const ADAPTER_MAP: Record<string, string> = {
  agent: 'Agent 自采集',
  prometheus: 'Prometheus',
  elk: 'ELK',
  skywalking: 'SkyWalking',
}

function adapterLabel(type: string): string {
  return ADAPTER_MAP[type] ?? type
}
function adapterColor(type: string): string {
  const map: Record<string, string> = {
    agent: '#409eff',
    prometheus: '#e6a23c',
    elk: '#67c23a',
    skywalking: '#f56c6c',
  }
  return map[type] ?? '#909399'
}
function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

async function loadStatus() {
  loading.value = true
  try {
    adapters.value = await listAdapterStatus()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function onTest(type: string) {
  testing.value = type
  try {
    const result = await testAdapter(type)
    if (result.ok) {
      ElMessage.success(`${adapterLabel(type)} 连通正常：${result.detail}`)
    } else {
      ElMessage.error(`${adapterLabel(type)} 连通失败：${result.detail}`)
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
