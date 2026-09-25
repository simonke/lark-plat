<template>
  <div class="page" v-loading="loading">
    <el-card>
      <template #header>
        <div class="toolbar">
          <div class="left">
            <el-button @click="goBack">返回</el-button>
            <span class="title">运行 #{{ runId }}</span>
            <el-tag v-if="run" :type="runStatusTag(run.status)" size="small">
              {{ runStatusLabel(run.status) }}
            </el-tag>
          </div>
          <div>
            <el-button :loading="loading" @click="load">刷新</el-button>
            <el-button v-if="canCancel" v-perm="'workflow:cancel'" type="warning" @click="onCancel">取消</el-button>
            <el-button v-perm="'workflow:run'" type="primary" @click="onRetry">重试</el-button>
          </div>
        </div>
      </template>

      <template v-if="run">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="运行 ID">{{ run.id }}</el-descriptions-item>
          <el-descriptions-item label="编排 ID">{{ run.workflow_id }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ run.workflow_version }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ runStatusLabel(run.status) }}</el-descriptions-item>
          <el-descriptions-item label="触发方式">{{ triggerLabel(run.trigger_type) }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ run.created_by ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatTime(run.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatTime(run.finished_at) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(run.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="错误" :span="3">{{ run.error || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">节点状态</el-divider>
        <el-table :data="nodes" border size="small">
          <el-table-column prop="node_key" label="节点" width="140" />
          <el-table-column label="类型" width="120">
            <template #default="{ row }">{{ nodeTypeLabel(row.node_type) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="nodeStatusTag(row.status)" size="small">{{ nodeStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="attempt" label="尝试" width="70" />
          <el-table-column label="执行任务" width="100">
            <template #default="{ row }">{{ row.exec_task_id ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="审批" width="100">
            <template #default="{ row }">{{ row.approval_id ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="开始" width="170">
            <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
          </el-table-column>
          <el-table-column label="结束" width="170">
            <template #default="{ row }">{{ formatTime(row.finished_at) }}</template>
          </el-table-column>
          <el-table-column label="错误" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">{{ row.error || '-' }}</template>
          </el-table-column>
        </el-table>
        <div v-if="!nodes.length" class="empty">（无节点）</div>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getWorkflowRun, cancelWorkflowRun, retryWorkflowRun } from '../../api/workflow'
import { extractError } from '../../api/http'
import type { WorkflowNodeRun, WorkflowRun } from '../../api/types'
import { formatTime, nodeStatusLabel, nodeStatusTag, nodeTypeLabel, runStatusLabel, runStatusTag, triggerLabel } from './helpers'

const route = useRoute()
const router = useRouter()
const runId = Number(route.params.id)

const loading = ref(false)
const run = ref<WorkflowRun | null>(null)
const nodes = ref<WorkflowNodeRun[]>([])
let timer: number | undefined

const canCancel = computed(() => run.value?.status === 'pending' || run.value?.status === 'running')

function scheduleRefresh() {
  if (timer) {
    window.clearInterval(timer)
    timer = undefined
  }
  const status = run.value?.status
  if (status === 'pending' || status === 'running') {
    timer = window.setInterval(load, 4000)
  }
}

async function load() {
  loading.value = true
  try {
    const detail = await getWorkflowRun(runId)
    run.value = detail.run
    nodes.value = detail.nodes
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
    scheduleRefresh()
  }
}

async function onCancel() {
  try {
    await ElMessageBox.confirm('确定取消该运行吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await cancelWorkflowRun(runId)
    ElMessage.success('已取消')
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function onRetry() {
  try {
    const res = await retryWorkflowRun(runId)
    ElMessage.success('已重试')
    router.push(`/workflow-runs/${res.run_id}`)
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

function goBack() {
  router.push('/workflow-runs')
}

onMounted(load)
onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.title {
  font-weight: 600;
}
.empty {
  color: var(--el-text-color-secondary);
  padding: 8px 0;
}
</style>
