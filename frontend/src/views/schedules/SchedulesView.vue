<template>
  <div class="schedules-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>定时任务</span>
          <el-button type="primary" @click="showCreateDialog" v-if="auth.hasPerm('schedule:add')">新建定时任务</el-button>
        </div>
      </template>

      <el-form :inline="true" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="query.name" placeholder="按名称过滤" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.enabled" placeholder="全部" clearable style="width: 130px">
            <el-option label="启用" :value="1" />
            <el-option label="停用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="80">
          <template #default="{ row }">{{ row.kind === 'script' ? '脚本' : '命令' }}</template>
        </el-table-column>
        <el-table-column label="触发方式" width="130">
          <template #default="{ row }">
            <span v-if="row.trigger_type === 'cron'">cron</span>
            <span v-else>间隔 {{ row.interval_sec }}s</span>
          </template>
        </el-table-column>
        <el-table-column label="表达式" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.cron_expr ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.enabled === 1 ? 'success' : 'info'">{{ row.enabled === 1 ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="timeout_sec" label="超时(s)" width="85" />
        <el-table-column prop="created_at" label="创建时间" min-width="165" show-overflow-tooltip />
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button size="small" @click="openRuns(row)" v-if="auth.hasPerm('schedule:list')">历史</el-button>
            <el-button size="small" type="primary" @click="handleRunNow(row)" v-if="auth.hasPerm('schedule:run')">立即执行</el-button>
            <el-button size="small" @click="showEditDialog(row)" v-if="auth.hasPerm('schedule:edit')">编辑</el-button>
            <el-button
              size="small"
              :type="row.enabled === 1 ? 'warning' : 'success'"
              @click="handleToggleStatus(row)"
              v-if="auth.hasPerm('schedule:edit')"
            >
              {{ row.enabled === 1 ? '停用' : '启用' }}
            </el-button>
            <el-popconfirm title="确定删除该定时任务吗？" @confirm="handleDelete(row)" v-if="auth.hasPerm('schedule:del')">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
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

    <el-dialog v-model="editVisible" :title="editingId ? '编辑定时任务' : '新建定时任务'" width="680px">
      <el-form :model="form" label-width="110px" ref="formRef" :rules="formRules">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="类型" prop="kind">
          <el-radio-group v-model="form.kind">
            <el-radio value="command">命令</el-radio>
            <el-radio value="script">脚本</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.kind === 'command'" label="命令内容" prop="command">
          <el-input v-model="form.command" type="textarea" :rows="3" placeholder="要执行的命令" />
        </el-form-item>
        <template v-else>
          <el-form-item label="选择脚本" prop="script_id">
            <el-select v-model="form.script_id" placeholder="请选择脚本" style="width: 100%" v-loading="scriptsLoading">
              <el-option v-for="s in scriptOptions" :key="s.id" :label="`${s.name} (v${s.current_version})`" :value="s.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="参数">
            <el-input v-model="form.paramsText" type="textarea" :rows="3" placeholder="可选，每行一个 key=value" />
          </el-form-item>
        </template>
        <el-form-item label="触发方式" prop="trigger_type">
          <el-radio-group v-model="form.trigger_type">
            <el-radio value="cron">cron 表达式</el-radio>
            <el-radio value="interval">固定间隔</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.trigger_type === 'cron'" label="cron 表达式" prop="cron_expr">
          <el-input v-model="form.cron_expr" placeholder="如：0 2 * * *（每天 02:00）" />
        </el-form-item>
        <el-form-item v-else label="间隔秒数" prop="interval_sec">
          <el-input-number v-model="form.interval_sec" :min="1" :max="86400" />
        </el-form-item>
        <el-form-item label="时区">
          <el-input v-model="form.timezone" placeholder="Asia/Shanghai" />
        </el-form-item>
        <el-form-item label="目标主机" prop="target_host_ids">
          <el-select
            v-model="form.target_host_ids"
            multiple
            filterable
            placeholder="请选择目标主机（可多选）"
            style="width: 100%"
            v-loading="hostsLoading"
          >
            <el-option v-for="h in hostOptions" :key="h.id" :label="`${h.hostname} (${h.ip})`" :value="h.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="超时(秒)">
          <el-input-number v-model="form.timeout_sec" :min="1" :max="86400" />
        </el-form-item>
        <el-form-item label="重试次数">
          <el-input-number v-model="form.retry" :min="0" :max="10" />
        </el-form-item>
        <el-form-item label="并发上限">
          <el-input-number v-model="form.concurrency_limit" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabledBool" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">提交</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="runsVisible" :title="`执行历史 - ${currentSchedule?.name ?? ''}`" size="60%">
      <el-table :data="runRows" v-loading="runsLoading" border size="small">
        <el-table-column prop="id" label="run_id" width="80" />
        <el-table-column prop="run_no" label="run_no" min-width="180" show-overflow-tooltip />
        <el-table-column prop="task_id" label="task_id" width="90" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="runStatusTagType(row.status)" size="small">{{ runStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" min-width="165" show-overflow-tooltip />
        <el-table-column prop="finished_at" label="结束时间" min-width="165" show-overflow-tooltip />
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              @click="handleRetryRun(row)"
              v-if="auth.hasPerm('schedule:retry') && canRetryRun(row)"
            >
              重试
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pagination"
        layout="total, prev, pager, next"
        :total="runsTotal"
        :current-page="runsQuery.page"
        :page-size="runsQuery.size"
        @current-change="onRunsPageChange"
      />
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  listSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  setScheduleStatus,
  runNow,
  listScheduleRuns,
  retryScheduleRun,
} from '../../api/schedule'
import { getScripts } from '../../api/scripts'
import { getHosts } from '../../api/assets'
import type { ScheduleOut, ScheduleCreate, ScheduleRunOut, ScriptOut, HostOut } from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()

const rows = ref<ScheduleOut[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ name: '', enabled: undefined as number | undefined, page: 1, size: 10 })

async function loadRows() {
  loading.value = true
  try {
    const page = await listSchedules({
      name: query.name || undefined,
      enabled: query.enabled,
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
  query.name = ''
  query.enabled = undefined
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

onMounted(() => {
  loadRows()
})

async function handleRunNow(row: ScheduleOut) {
  try {
    await runNow(row.id)
    ElMessage.success('已触发立即执行')
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function handleToggleStatus(row: ScheduleOut) {
  try {
    await setScheduleStatus(row.id, row.enabled === 1 ? 0 : 1)
    ElMessage.success(row.enabled === 1 ? '已停用' : '已启用')
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function handleDelete(row: ScheduleOut) {
  try {
    await deleteSchedule(row.id)
    ElMessage.success('已删除')
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const editVisible = ref(false)
const editingId = ref<number | null>(null)
const editingRow = ref<ScheduleOut | null>(null)
const formRef = ref()
const submitLoading = ref(false)
const form = reactive({
  name: '',
  kind: 'command' as 'command' | 'script',
  command: '',
  script_id: undefined as number | undefined,
  paramsText: '',
  trigger_type: 'cron' as 'cron' | 'interval',
  cron_expr: '',
  timezone: 'Asia/Shanghai',
  interval_sec: 3600,
  target_host_ids: [] as number[],
  timeout_sec: 300,
  retry: 0,
  concurrency_limit: 10,
  enabledBool: true,
})
const formRules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  command: [{ required: true, message: '请输入命令内容', trigger: 'blur' }],
  script_id: [{ required: true, message: '请选择脚本', trigger: 'change' }],
  cron_expr: [{ required: true, message: '请输入 cron 表达式', trigger: 'blur' }],
  interval_sec: [{ required: true, message: '请输入间隔秒数', trigger: 'change' }],
  target_host_ids: [{ required: true, type: 'array', min: 1, message: '请至少选择一台目标主机', trigger: 'change' }],
}

const scriptOptions = ref<ScriptOut[]>([])
const scriptsLoading = ref(false)
const hostOptions = ref<HostOut[]>([])
const hostsLoading = ref(false)

async function loadOptions() {
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

function resetForm() {
  Object.assign(form, {
    name: '',
    kind: 'command',
    command: '',
    script_id: undefined,
    paramsText: '',
    trigger_type: 'cron',
    cron_expr: '',
    timezone: 'Asia/Shanghai',
    interval_sec: 3600,
    target_host_ids: [],
    timeout_sec: 300,
    retry: 0,
    concurrency_limit: 10,
    enabledBool: true,
  })
}

function idsToCounts(ids: Record<string, unknown> | null | undefined): number[] {
  if (!ids) return []
  if (Array.isArray(ids.ids)) return ids.ids as number[]
  const raw = ids.ids as Record<string, unknown> | number
  if (typeof raw === 'number') return [raw]
  if (raw && typeof raw === 'object') {
    return Object.keys(raw).map(Number).filter((n) => Number.isFinite(n) && n > 0)
  }
  return []
}

function showCreateDialog() {
  resetForm()
  editingId.value = null
  editingRow.value = null
  editVisible.value = true
  loadOptions()
}

function showEditDialog(row: ScheduleOut) {
  editingId.value = row.id
  editingRow.value = row
  Object.assign(form, {
    name: row.name,
    kind: row.kind as 'command' | 'script',
    command: row.command ?? '',
    script_id: row.script_id ?? undefined,
    paramsText: row.params ? Object.entries(row.params).map(([k, v]) => `${k}=${v}`).join('\n') : '',
    trigger_type: row.trigger_type as 'cron' | 'interval',
    cron_expr: row.cron_expr ?? '',
    timezone: row.timezone,
    interval_sec: row.interval_sec ?? 3600,
    target_host_ids: idsToCounts(row.target_host_ids),
    timeout_sec: row.timeout_sec,
    retry: row.retry,
    concurrency_limit: row.concurrency_limit,
    enabledBool: row.enabled === 1,
  })
  editVisible.value = true
  loadOptions()
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

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    const basePayload = {
      name: form.name,
      kind: form.kind,
      command: form.kind === 'command' ? form.command : null,
      script_id: form.kind === 'script' ? (form.script_id ?? null) : null,
      params: form.kind === 'script' ? parseParams(form.paramsText) : null,
      trigger_type: form.trigger_type,
      cron_expr: form.trigger_type === 'cron' ? form.cron_expr : null,
      timezone: form.timezone,
      interval_sec: form.trigger_type === 'interval' ? form.interval_sec : null,
      target_host_ids: form.target_host_ids,
      timeout_sec: form.timeout_sec,
      retry: form.retry,
      concurrency_limit: form.concurrency_limit,
    } as ScheduleCreate
    if (editingId.value) {
      const { enabled: _ignore, ...updatePayload } = basePayload
      void _ignore
      await updateSchedule(editingId.value, updatePayload)
      if (form.enabledBool !== (editingRow.value?.enabled === 1)) {
        await setScheduleStatus(editingId.value, form.enabledBool ? 1 : 0)
      }
      ElMessage.success('已保存')
    } else {
      await createSchedule({ ...basePayload, enabled: form.enabledBool ? 1 : 0 })
      ElMessage.success('已创建')
    }
    editVisible.value = false
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

const runsVisible = ref(false)
const currentSchedule = ref<ScheduleOut | null>(null)
const runRows = ref<ScheduleRunOut[]>([])
const runsTotal = ref(0)
const runsLoading = ref(false)
const runsQuery = reactive({ page: 1, size: 10 })

function runStatusLabel(status: string): string {
  const map: Record<string, string> = { running: '执行中', success: '成功', failed: '失败', canceled: '已取消', timed_out: '超时' }
  return map[status] ?? status
}

function runStatusTagType(status: string): string {
  const map: Record<string, string> = { running: 'primary', success: 'success', failed: 'danger', canceled: 'info', timed_out: 'danger' }
  return map[status] ?? 'info'
}

function canRetryRun(row: ScheduleRunOut): boolean {
  return ['failed', 'timed_out', 'canceled'].includes(row.status)
}

async function openRuns(row: ScheduleOut) {
  currentSchedule.value = row
  runsVisible.value = true
  runsQuery.page = 1
  loadRuns()
}

async function loadRuns() {
  if (!currentSchedule.value) return
  runsLoading.value = true
  try {
    const page = await listScheduleRuns(currentSchedule.value.id, { page: runsQuery.page, size: runsQuery.size })
    runRows.value = page.list
    runsTotal.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    runsLoading.value = false
  }
}

function onRunsPageChange(page: number) {
  runsQuery.page = page
  loadRuns()
}

async function handleRetryRun(row: ScheduleRunOut) {
  if (!currentSchedule.value) return
  try {
    await retryScheduleRun(currentSchedule.value.id, row.id)
    ElMessage.success('重试已触发')
    loadRuns()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}
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
</style>