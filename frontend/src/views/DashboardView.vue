<template>
  <div class="dashboard-view">
    <h3>仪表盘</h3>

    <el-row :gutter="20" class="stats-row" v-loading="statsLoading">
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #409eff">
              <el-icon :size="24"><Monitor /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.host_total ?? 0 }}</div>
              <div class="stat-label">主机总数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #67c23a">
              <el-icon :size="24"><CircleCheck /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.host_online ?? 0 }}</div>
              <div class="stat-label">在线主机</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f56c6c">
              <el-icon :size="24"><VideoPlay /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.tasks_running ?? 0 }}</div>
              <div class="stat-label">执行中任务</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #e6a23c">
              <el-icon :size="24"><Calendar /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.today_tasks ?? 0 }}</div>
              <div class="stat-label">今日任务</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #909399">
              <el-icon :size="24"><CircleCheckFilled /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.today_success ?? 0 }}</div>
              <div class="stat-label">今日成功</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="4">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f56c6c">
              <el-icon :size="24"><Finished /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.pending_approvals ?? 0 }}</div>
              <div class="stat-label">待审批</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="trend-row">
      <el-col :span="14">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>任务趋势（近 7 天）</span>
              <el-select v-model="trendDays" style="width: 100px" @change="loadTrend">
                <el-option label="7 天" :value="7" />
                <el-option label="14 天" :value="14" />
                <el-option label="30 天" :value="30" />
              </el-select>
            </div>
          </template>
          <div ref="trendEl" class="trend-chart" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card>
          <template #header>
            <span>快速操作</span>
          </template>
          <div class="action-list">
            <el-button type="primary" @click="$router.push('/assets/hosts')" v-if="auth.hasPerm('asset:host:list')">
              <el-icon><Monitor /></el-icon> 主机管理
            </el-button>
            <el-button type="success" @click="$router.push('/exec/tasks')" v-if="auth.hasPerm('exec:task:list')">
              <el-icon><VideoPlay /></el-icon> 任务中心
            </el-button>
            <el-button type="warning" @click="$router.push('/schedules')" v-if="auth.hasPerm('schedule:list')">
              <el-icon><Calendar /></el-icon> 定时任务
            </el-button>
            <el-button type="danger" @click="$router.push('/operations/approvals')" v-if="auth.hasPerm('approval:view')">
              <el-icon><Finished /></el-icon> 审批中心
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="recent-row">
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近任务</span>
              <el-button link type="primary" @click="$router.push('/exec/tasks')" v-if="auth.hasPerm('exec:task:list')">更多</el-button>
            </div>
          </template>
          <el-table :data="recentTasks" size="small" v-loading="recentLoading">
            <el-table-column prop="task_no" label="任务编号" min-width="140" show-overflow-tooltip />
            <el-table-column prop="name" label="名称" min-width="120" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="taskStatusTagType(row.status)" size="small">{{ taskStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" min-width="150" show-overflow-tooltip />
          </el-table>
          <el-empty v-if="recentTasks.length === 0" description="暂无任务" :image-size="60" />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>最近审批</span>
              <el-button link type="primary" @click="$router.push('/operations/approvals')" v-if="auth.hasPerm('approval:view')">更多</el-button>
            </div>
          </template>
          <el-table :data="recentApprovals" size="small" v-loading="recentLoading">
            <el-table-column prop="request_no" label="请求编号" min-width="140" show-overflow-tooltip />
            <el-table-column prop="title" label="标题" min-width="140" show-overflow-tooltip />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="approvalStatusTagType(row.status)" size="small">{{ approvalStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" min-width="150" show-overflow-tooltip />
          </el-table>
          <el-empty v-if="recentApprovals.length === 0" description="暂无审批" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Monitor, CircleCheck, VideoPlay, Calendar, CircleCheckFilled, Finished } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { getDashboardStats, getTaskTrend, getRecentTasks, getRecentApprovals } from '../api/dashboard'
import type { DashboardStats, TrendPoint, RecentTask, RecentApproval } from '../api/types'

echarts.use([LineChart, TooltipComponent, LegendComponent, GridComponent, CanvasRenderer])

type ChartType = ReturnType<typeof echarts.init>
let chart: ChartType | null = null

const auth = useAuthStore()

const stats = ref<DashboardStats | null>(null)
const statsLoading = ref(false)
const trend = ref<TrendPoint[]>([])
const trendDays = ref(7)
const recentTasks = ref<RecentTask[]>([])
const recentApprovals = ref<RecentApproval[]>([])
const recentLoading = ref(false)

const trendEl = ref<HTMLElement>()

const TASK_STATUS_MAP: Record<string, string> = {
  created: '已创建',
  awaiting_approval: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  running: '执行中',
  success: '成功',
  partial: '部分成功',
  failed: '失败',
  canceled: '已取消',
  timed_out: '已超时',
}
const TASK_STATUS_TAG: Record<string, string> = {
  created: 'info',
  awaiting_approval: 'warning',
  approved: 'primary',
  rejected: 'danger',
  running: 'primary',
  success: 'success',
  partial: 'warning',
  failed: 'danger',
  canceled: 'info',
  timed_out: 'danger',
}
const APPROVAL_STATUS_MAP: Record<string, string> = {
  pending: '待审批',
  approved: '已批准',
  rejected: '已拒绝',
  canceled: '已取消',
}
const APPROVAL_STATUS_TAG: Record<string, string> = {
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  canceled: 'info',
}

function taskStatusLabel(status: string): string {
  return TASK_STATUS_MAP[status] ?? status
}
function taskStatusTagType(status: string): string {
  return TASK_STATUS_TAG[status] ?? 'info'
}
function approvalStatusLabel(status: string): string {
  return APPROVAL_STATUS_MAP[status] ?? status
}
function approvalStatusTagType(status: string): string {
  return APPROVAL_STATUS_TAG[status] ?? 'info'
}

function renderChart() {
  if (!trendEl.value) return
  if (!chart) {
    chart = echarts.init(trendEl.value)
  }
  chart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['总数', '成功', '失败'] },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: trend.value.map((t) => t.date) },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '总数', type: 'line', smooth: true, data: trend.value.map((t) => t.total), itemStyle: { color: '#409eff' } },
      { name: '成功', type: 'line', smooth: true, data: trend.value.map((t) => t.success), itemStyle: { color: '#67c23a' } },
      { name: '失败', type: 'line', smooth: true, data: trend.value.map((t) => t.failed), itemStyle: { color: '#f56c6c' } },
    ],
  })
}

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getDashboardStats()
  } catch {
    stats.value = null
  } finally {
    statsLoading.value = false
  }
}

async function loadTrend() {
  try {
    trend.value = await getTaskTrend(trendDays.value)
    renderChart()
  } catch {
    trend.value = []
  }
}

async function loadRecent() {
  recentLoading.value = true
  try {
    const [tasks, approvals] = await Promise.all([getRecentTasks(), getRecentApprovals()])
    recentTasks.value = tasks
    recentApprovals.value = approvals
  } catch {
    recentTasks.value = []
    recentApprovals.value = []
  } finally {
    recentLoading.value = false
  }
}

function onResize() {
  chart?.resize()
}

onMounted(async () => {
  await Promise.all([loadStats(), loadTrend(), loadRecent()])
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
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
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
}
.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}
.trend-row {
  margin-bottom: 20px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.trend-chart {
  height: 300px;
}
.action-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.action-list .el-button {
  justify-content: flex-start;
}
</style>