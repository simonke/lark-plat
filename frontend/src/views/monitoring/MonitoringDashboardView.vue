<template>
  <div class="dashboard-view">
    <h3>监控告警</h3>

    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #409eff">
              <el-icon :size="24"><DataLine /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ alertStats.firing }}</div>
              <div class="stat-label">触发中告警</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f56c6c">
              <el-icon :size="24"><Warning /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ alertStats.critical }}</div>
              <div class="stat-label">严重</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #e6a23c">
              <el-icon :size="24"><Bell /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ alertStats.warning }}</div>
              <div class="stat-label">警告</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #67c23a">
              <el-icon :size="24"><CircleCheck /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ wsConnected ? '在线' : '离线' }}</div>
              <div class="stat-label">实时推送</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="chart-row">
      <el-col :span="16">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>指标趋势</span>
              <div>
                <el-select v-model="metricName" style="width: 200px" @change="loadMetrics">
                  <el-option label="CPU 使用率(%)" value="cpu_usage_percent" />
                  <el-option label="内存使用率(%)" value="memory_usage_percent" />
                  <el-option label="服务响应时间(ms)" value="service_resp_time" />
                </el-select>
                <el-button class="refresh-btn" size="small" @click="loadMetrics">刷新</el-button>
              </div>
            </div>
          </template>
          <div ref="trendEl" class="trend-chart" />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>
            <span>实时告警流</span>
          </template>
          <div class="alert-stream" v-loading="alertLoading">
            <el-empty v-if="realtimeAlerts.length === 0" description="暂无实时告警" :image-size="50" />
            <div v-for="item in realtimeAlerts" :key="item.id" class="stream-item">
              <el-tag :type="severityTag(item.severity)" size="small">{{ item.severity }}</el-tag>
              <span class="stream-text">{{ item.rule_name ?? item.entity?.entity_name }}</span>
              <span class="stream-time">{{ shortTime(item.ts) }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="card-gap">
      <template #header>
        <div class="card-header">
          <span>告警事件</span>
          <el-button link type="primary" @click="$router.push('/monitor/alerts')" v-perm="'monitor:alert:list'">更多</el-button>
        </div>
      </template>
      <el-table :data="recentAlerts" size="small" v-loading="alertLoading">
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
        <el-table-column label="对象" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">{{ row.entity?.entity_name ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="rule_name" label="规则" min-width="140" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近时间" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.ts ?? '-' }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { DataLine, Warning, Bell, CircleCheck } from '@element-plus/icons-vue'
import { getMetrics, listAlerts, getMonitoringWsToken } from '../../api/monitoring'
import { buildMetricSeries } from './metricSeries'
import type { MonAlertOut, MonMetricResult, MonWsFrame } from '../../api/types'

echarts.use([LineChart, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

type ChartType = ReturnType<typeof echarts.init>
let chart: ChartType | null = null

const trendEl = ref<HTMLElement>()
const metricName = ref('cpu_usage_percent')
const metricResult = ref<MonMetricResult | null>(null)

const alertLoading = ref(false)
const recentAlerts = ref<MonAlertOut[]>([])
const realtimeAlerts = ref<MonAlertOut[]>([])
const wsConnected = ref(false)

const alertStats = computed(() => {
  const firing = recentAlerts.value.filter((a) => a.status === 'firing').length
  const critical = recentAlerts.value.filter((a) => a.severity === 'critical').length
  const warning = recentAlerts.value.filter((a) => a.severity === 'warning').length
  return { firing, critical, warning }
})

// 后端 /monitor/metrics：不传 agg → 原始采样点（含 entity_id/source）；传 agg → 分桶点
// 契约冻结 agg 点为 {ts,value}，附加键 bucket/avg/entity_id 容错解析（架构师裁定 C）
const chartSeries = computed(() => buildMetricSeries(metricResult.value, metricName.value))

const SOURCE_MAP: Record<string, string> = {
  agent: 'Agent',
  prometheus: 'Prometheus',
  alertmanager: 'Alertmanager',
  elk: 'ELK',
  skywalking: 'SkyWalking',
  webhook: 'Webhook',
}
const SEVERITY_MAP: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '信息',
}
const STATUS_MAP: Record<string, string> = {
  pending: '待评估',
  firing: '触发中',
  acknowledged: '已确认',
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
  const map: Record<string, string> = {
    pending: 'info',
    firing: 'danger',
    acknowledged: 'warning',
    resolved: 'success',
  }
  return map[st] ?? 'info'
}
function shortTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleTimeString() : ''
}

function renderChart() {
  if (!trendEl.value) return
  if (!chart) chart = echarts.init(trendEl.value)
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll' },
    grid: { left: 60, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'time' },
    yAxis: { type: 'value' },
    series: chartSeries.value.map((s) => ({
      name: s.name,
      type: 'line' as const,
      smooth: true,
      showSymbol: false,
      data: s.data,
    })),
  }, true)
}

async function loadMetrics() {
  try {
    metricResult.value = await getMetrics({ metric_name: metricName.value, size: 500 })
  } catch {
    metricResult.value = null
  }
  renderChart()
}

async function loadAlerts() {
  alertLoading.value = true
  try {
    const page = await listAlerts({ size: 10 })
    recentAlerts.value = page.list
  } catch {
    recentAlerts.value = []
  } finally {
    alertLoading.value = false
  }
}

let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let pingTimer: ReturnType<typeof setInterval> | null = null

async function connectWs() {
  try {
    const token = await getMonitoringWsToken()
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${window.location.host}/api/v1/ws/monitor?token=${encodeURIComponent(token)}`)
    socket = ws
    ws.onopen = () => {
      wsConnected.value = true
      startPing()
      sendFrame({ type: 'subscribe', data: {} })
    }
    ws.onmessage = (ev: MessageEvent<string>) => {
      let frame: MonWsFrame
      try {
        frame = JSON.parse(ev.data) as MonWsFrame
      } catch {
        return
      }
      if (frame.type === 'alert' && frame.data) {
        realtimeAlerts.value.unshift(frame.data as MonAlertOut)
        if (realtimeAlerts.value.length > 20) realtimeAlerts.value.pop()
      }
    }
    ws.onclose = () => {
      wsConnected.value = false
      socket = null
      stopPing()
      scheduleReconnect()
    }
    ws.onerror = () => {
      ws.close()
    }
  } catch {
    scheduleReconnect()
  }
}

function sendFrame(payload: unknown) {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(payload))
  }
}

function startPing() {
  stopPing()
  pingTimer = setInterval(() => {
    sendFrame({ type: 'ping' })
  }, 30_000)
}

function stopPing() {
  if (pingTimer !== null) {
    clearInterval(pingTimer)
    pingTimer = null
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectWs()
  }, 5000)
}

function stopWs() {
  if (socket) {
    socket.onclose = null
    socket.close(1000)
    socket = null
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  stopPing()
}

function onResize() {
  chart?.resize()
}

onMounted(async () => {
  await Promise.all([loadMetrics(), loadAlerts()])
  connectWs()
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  stopWs()
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.dashboard-view {
  padding: 20px;
}
.stats-row {
  margin-bottom: 20px;
}
.stat-card {
  cursor: pointer;
  height: 100%;
}
.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.stat-info {
  flex: 1;
}
.stat-value {
  font-size: 24px;
  font-weight: 600;
  line-height: 1.2;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 4px;
}
.chart-row {
  margin-bottom: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.refresh-btn {
  margin-left: 8px;
}
.trend-chart {
  height: 320px;
}
.alert-stream {
  max-height: 320px;
  overflow-y: auto;
}
.stream-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.stream-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.stream-time {
  color: #909399;
  font-size: 12px;
}
.card-gap {
  margin-top: 16px;
}
</style>
