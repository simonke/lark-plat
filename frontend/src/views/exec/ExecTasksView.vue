<template>
  <div class="exec-tasks-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>任务中心</span>
          <el-button type="primary" @click="showCreateDialog" v-if="auth.hasPerm('exec:task:run')">新建任务</el-button>
        </div>
      </template>

      <el-form :inline="true" @submit.prevent>
        <el-form-item label="任务编号">
          <el-input v-model="query.task_no" placeholder="按编号过滤" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="query.name" placeholder="按名称过滤" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable style="width: 160px">
            <el-option v-for="s in TASK_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="query.kind" placeholder="全部" clearable style="width: 130px">
            <el-option label="命令" value="command" />
            <el-option label="脚本" value="script" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch" v-if="auth.hasPerm('exec:task:list')">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="task_no" label="任务编号" min-width="150" show-overflow-tooltip />
        <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">{{ row.kind === 'script' ? '脚本' : '命令' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="敏感/审批" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.approve_required === 1" type="warning" size="small">需审批</el-tag>
            <el-tag v-else-if="row.sensitive_flag === 1" type="info" size="small">敏感</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="mode" label="模式" width="80" />
        <el-table-column prop="timeout_sec" label="超时(s)" width="85" />
        <el-table-column prop="created_at" label="创建时间" min-width="165" show-overflow-tooltip />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)" v-if="auth.hasPerm('exec:task:log')">详情</el-button>
            <el-popconfirm
              title="确定停止该任务吗？"
              @confirm="handleStop(row)"
              v-if="canStop(row)"
            >
              <template #reference>
                <el-button size="small" type="warning">停止</el-button>
              </template>
            </el-popconfirm>
            <el-popconfirm
              title="确定重试该任务吗？"
              @confirm="handleRetry(row)"
              v-if="canRetry(row)"
            >
              <template #reference>
                <el-button size="small" type="primary">重试</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pagination"
        layout="total, prev, pager, next, sizes"
        :total="total"
        :current-page="query.page"
        :page-size="query.size"
        :page-sizes="[10, 20, 50]"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
    </el-card>

    <el-dialog v-model="createVisible" title="新建执行任务" width="640px">
      <el-form :model="createForm" label-width="100px" ref="createFormRef" :rules="createRules">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="类型" prop="kind">
          <el-radio-group v-model="createForm.kind">
            <el-radio value="command">命令</el-radio>
            <el-radio value="script">脚本</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createForm.kind === 'command'" label="命令内容" prop="command">
          <el-input v-model="createForm.command" type="textarea" :rows="4" placeholder="要执行的命令" />
        </el-form-item>
        <template v-else>
          <el-form-item label="选择脚本" prop="script_id">
            <el-select v-model="createForm.script_id" placeholder="请选择脚本" style="width: 320px" v-loading="scriptsLoading">
              <el-option
                v-for="s in scriptOptions"
                :key="s.id"
                :label="`${s.name} (v${s.current_version})`"
                :value="s.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="指定版本">
            <el-input-number v-model="createForm.script_version" :min="1" placeholder="留空用当前版本" />
          </el-form-item>
          <el-form-item label="参数">
            <el-input
              v-model="createForm.paramsText"
              type="textarea"
              :rows="3"
              placeholder="可选，每行一个：key=value"
            />
          </el-form-item>
        </template>
        <el-form-item label="目标主机" prop="target_host_ids">
          <el-select
            v-model="createForm.target_host_ids"
            multiple
            filterable
            placeholder="请选择目标主机（可多选）"
            style="width: 100%"
            v-loading="hostsLoading"
          >
            <el-option
              v-for="h in hostOptions"
              :key="h.id"
              :label="`${h.hostname} (${h.ip})${h.sensitivity_level === 'sensitive' ? ' ★' : ''}`"
              :value="h.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="模式">
          <el-radio-group v-model="createForm.mode">
            <el-radio value="batch">batch</el-radio>
            <el-radio value="single">single</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="超时(秒)">
          <el-input-number v-model="createForm.timeout_sec" :min="1" :max="86400" />
        </el-form-item>
        <el-form-item label="重试次数">
          <el-input-number v-model="createForm.retry" :min="0" :max="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleCreate">提交</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" :title="`任务详情 - ${detail?.task_no ?? ''}`" size="62%">
      <div v-loading="detailLoading">
        <template v-if="detail">
        <el-alert
          v-if="detail.status === 'awaiting_approval'"
          type="warning"
          :closable="false"
          title="该任务待审批，请在审批中心完成审批后继续"
          class="approval-hint"
        />
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)">{{ statusLabel(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="审批状态">{{ detail.approval_status ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="模式">{{ detail.mode }}</el-descriptions-item>
          <el-descriptions-item label="超时(秒)">{{ detail.timeout_sec }}</el-descriptions-item>
          <el-descriptions-item label="重试次数">{{ detail.retry }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ detail.started_at ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ detail.finished_at ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="审批单ID">{{ detail.approval_id ?? '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-descriptions v-if="detail.kind === 'command'" :column="1" border size="small" class="block-gap">
          <el-descriptions-item label="命令">{{ detail.command }}</el-descriptions-item>
        </el-descriptions>
        <el-descriptions v-else :column="2" border size="small" class="block-gap">
          <el-descriptions-item label="脚本ID">{{ detail.script_id }}</el-descriptions-item>
          <el-descriptions-item label="脚本版本">{{ detail.script_version ?? '当前' }}</el-descriptions-item>
          <el-descriptions-item label="参数">{{ detail.params ? JSON.stringify(detail.params) : '-' }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">执行统计</h4>
        <div v-if="detailStats" class="stats-row">
          <el-tag type="info" size="small">总任务 {{ detailStats.total }}</el-tag>
          <el-tag type="info" size="small">等待 {{ detailStats.pending }}</el-tag>
          <el-tag type="primary" size="small">执行中 {{ detailStats.running }}</el-tag>
          <el-tag type="success" size="small">成功 {{ detailStats.success }}</el-tag>
          <el-tag type="danger" size="small">失败 {{ detailStats.failed }}</el-tag>
          <el-tag type="danger" size="small">超时 {{ detailStats.timed_out }}</el-tag>
          <el-tag type="info" size="small">取消 {{ detailStats.canceled }}</el-tag>
        </div>
        <div v-else class="stats-row">
          <span class="stats-empty">暂无统计</span>
        </div>

        <h4 class="section-title">目标主机（点击「日志」查看实时输出）</h4>
        <el-table :data="detail.hosts" border size="small">
          <el-table-column prop="id" label="task_host_id" width="110" />
          <el-table-column prop="hostname" label="主机名" min-width="120" show-overflow-tooltip />
          <el-table-column prop="ip" label="IP" min-width="110" />
          <el-table-column prop="executor" label="执行器" width="80" />
          <el-table-column label="状态" width="95">
            <template #default="{ row }">
              <el-tag :type="hostStatusTagType(row.status)" size="small">{{ hostStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="exit_code" label="退出码" width="75" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button size="small" @click="openLogViewer(row)" v-if="auth.hasPerm('exec:task:log')">日志</el-button>
            </template>
          </el-table-column>
        </el-table>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="logVisible" :title="`实时日志 - ${logHost?.hostname ?? ''} (task_host_id=${logHost?.id ?? ''})`" width="760px" @closed="stopLogViewer">
      <div class="log-toolbar">
        <el-tag :type="logConnected ? 'success' : 'info'" size="small">
          {{ logConnected ? '已连接' : '未连接' }}
        </el-tag>
        <span class="log-lines">共 {{ logLines.length }} 行</span>
      </div>
      <div ref="logContainer" class="log-container">
        <div v-for="line in logLines" :key="line.seq" class="log-line">
          <span class="log-seq">#{{ line.seq }}</span>
          <span :class="['log-content', line.level === 'error' ? 'is-error' : '']">{{ line.content }}</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { getTasks, createTask, getTask, stopTask, retryTask, getTaskStats } from '../../api/exec'
import { getScripts } from '../../api/scripts'
import { getHosts } from '../../api/assets'
import { useRealtimeLog } from '../../composables/useRealtimeLog'
import type { ExecTaskOut, ExecTaskDetail, ExecTaskCreate, ExecStats, ScriptOut, HostOut } from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()

const TASK_STATUSES = [
  { value: 'created', label: '已创建' },
  { value: 'awaiting_approval', label: '待审批' },
  { value: 'approved', label: '已审批' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'running', label: '执行中' },
  { value: 'success', label: '成功' },
  { value: 'partial', label: '部分成功' },
  { value: 'failed', label: '失败' },
  { value: 'canceled', label: '已取消' },
  { value: 'timed_out', label: '已超时' },
]

const STATUS_TAG_TYPES: Record<string, string> = {
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

function statusLabel(status: string): string {
  return TASK_STATUSES.find((s) => s.value === status)?.label ?? status
}

function statusTagType(status: string): string {
  return STATUS_TAG_TYPES[status] ?? 'info'
}

function hostStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '等待',
    running: '执行中',
    success: '成功',
    failed: '失败',
    timed_out: '超时',
    canceled: '取消',
  }
  return map[status] ?? status
}

function hostStatusTagType(status: string): string {
  const map: Record<string, string> = {
    pending: 'info',
    running: 'primary',
    success: 'success',
    failed: 'danger',
    timed_out: 'danger',
    canceled: 'info',
  }
  return map[status] ?? 'info'
}

function canStop(task: ExecTaskOut): boolean {
  return auth.hasPerm('exec:task:stop') && ['running'].includes(task.status)
}

function canRetry(task: ExecTaskOut): boolean {
  return auth.hasPerm('exec:task:retry') && ['failed', 'timed_out', 'canceled'].includes(task.status)
}

const rows = ref<ExecTaskOut[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ task_no: '', name: '', status: '', kind: '', page: 1, size: 10 })

async function loadRows() {
  loading.value = true
  try {
    const page = await getTasks({
      task_no: query.task_no || undefined,
      name: query.name || undefined,
      status: query.status || undefined,
      kind: query.kind || undefined,
      page: query.page,
      size: query.size,
    })
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  query.page = 1
  loadRows()
}

function handleReset() {
  query.task_no = ''
  query.name = ''
  query.status = ''
  query.kind = ''
  query.page = 1
  loadRows()
}

function onPageChange(page: number) {
  query.page = page
  loadRows()
}

function onSizeChange(size: number) {
  query.size = size
  query.page = 1
  loadRows()
}

async function handleStop(task: ExecTaskOut) {
  try {
    await stopTask(task.id)
    ElMessage.success('停止指令已下发')
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function handleRetry(task: ExecTaskOut) {
  try {
    await retryTask(task.id)
    ElMessage.success('重试已发起')
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const createVisible = ref(false)
const createFormRef = ref()
const submitLoading = ref(false)
const createForm = reactive({
  name: '',
  kind: 'command' as 'command' | 'script',
  command: '',
  script_id: undefined as number | undefined,
  script_version: undefined as number | undefined,
  paramsText: '',
  target_host_ids: [] as number[],
  mode: 'batch',
  timeout_sec: 300,
  retry: 0,
})
const createRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  command: [{ required: true, message: '请输入命令内容', trigger: 'blur' }],
  script_id: [{ required: true, message: '请选择脚本', trigger: 'change' }],
  target_host_ids: [{ required: true, type: 'array', min: 1, message: '请至少选择一台目标主机', trigger: 'change' }],
}

const scriptOptions = ref<ScriptOut[]>([])
const scriptsLoading = ref(false)
const hostOptions = ref<HostOut[]>([])
const hostsLoading = ref(false)

async function showCreateDialog() {
  Object.assign(createForm, {
    name: '',
    kind: 'command',
    command: '',
    script_id: undefined,
    script_version: undefined,
    paramsText: '',
    target_host_ids: [],
    mode: 'batch',
    timeout_sec: 300,
    retry: 0,
  })
  createVisible.value = true
  if (auth.hasPerm('script:list')) {
    scriptsLoading.value = true
    try {
      const page = await getScripts({ page: 1, size: 100 })
      scriptOptions.value = page.list
    } catch {
      scriptOptions.value = []
    } finally {
      scriptsLoading.value = false
    }
  }
  hostsLoading.value = true
  try {
    const page = await getHosts({ page: 1, size: 100 })
    hostOptions.value = page.list
  } catch {
    hostOptions.value = []
  } finally {
    hostsLoading.value = false
  }
}

async function handleCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const payload: ExecTaskCreate = {
      name: createForm.name,
      kind: createForm.kind,
      command: createForm.kind === 'command' ? createForm.command : null,
      script_id: createForm.kind === 'script' ? (createForm.script_id ?? null) : null,
      script_version: createForm.kind === 'script' ? (createForm.script_version ?? null) : null,
      params: createForm.kind === 'script' ? parseParams(createForm.paramsText) : null,
      target_host_ids: createForm.target_host_ids,
      mode: createForm.mode,
      timeout_sec: createForm.timeout_sec,
      retry: createForm.retry,
    }
    await createTask(payload)
    ElMessage.success('任务已创建')
    createVisible.value = false
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

function parseParams(text: string): Record<string, string> | null {
  const out: Record<string, string> = {}
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const idx = line.indexOf('=')
    if (idx > 0) out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
    else out[line] = ''
  }
  return Object.keys(out).length > 0 ? out : null
}

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<ExecTaskDetail | null>(null)
const detailStats = ref<ExecStats | null>(null)

async function openDetail(row: ExecTaskOut) {
  detailVisible.value = true
  detailLoading.value = true
  detailStats.value = null
  try {
    detail.value = await getTask(row.id)
    try {
      detailStats.value = await getTaskStats(row.id)
    } catch {
      detailStats.value = null
    }
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    detailLoading.value = false
  }
}

const logVisible = ref(false)
const logHost = ref<{ id: number; hostname: string } | null>(null)
const logContainer = ref<HTMLElement>()
let logSession: ReturnType<typeof useRealtimeLog> | null = null
const sessionVersion = ref(0)
const logLines = computed(() => {
  void sessionVersion.value
  return logSession?.lines.value ?? []
})
const logConnected = computed(() => {
  void sessionVersion.value
  return logSession?.connected.value ?? false
})

function openLogViewer(host: { id: number; hostname: string }) {
  if (!detail.value) return
  stopLogViewer()
  logHost.value = host
  logVisible.value = true
  logSession = useRealtimeLog({
    taskId: detail.value.id,
    taskHostId: host.id,
    onStatus: (status) => {
      ElMessage.info(`主机执行状态：${status}`)
    },
  })
  sessionVersion.value += 1
  void nextTick(() => scrollToBottom())
  logSession.start()
}

function stopLogViewer() {
  logSession?.stop()
  logSession = null
  sessionVersion.value += 1
  logHost.value = null
}

function scrollToBottom() {
  const el = logContainer.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => logSession?.lines.value.length ?? 0,
  () => {
    void nextTick(() => scrollToBottom())
  },
)

onBeforeUnmount(() => {
  stopLogViewer()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pagination {
  margin-top: 12px;
  justify-content: flex-end;
}
.approval-hint {
  margin-bottom: 12px;
}
.block-gap {
  margin-top: 12px;
}
.section-title {
  margin: 16px 0 8px;
}
.stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 4px;
}
.stats-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.log-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.log-lines {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.log-container {
  height: 380px;
  overflow-y: auto;
  background: #0d1117;
  border-radius: 4px;
  padding: 8px 12px;
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
}
.log-line {
  line-height: 20px;
  white-space: pre-wrap;
  word-break: break-all;
}
.log-seq {
  display: inline-block;
  width: 56px;
  color: #6b7280;
}
.log-content {
  color: #d1d5db;
}
.log-content.is-error {
  color: #f87171;
}
</style>
