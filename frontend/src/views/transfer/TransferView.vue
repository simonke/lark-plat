<template>
  <div class="transfer-view">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="包管理" name="packages">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>文件包管理</span>
              <div>
                <el-button type="primary" @click="pickFiles" v-if="auth.hasPerm('transfer:package:add')">上传包</el-button>
                <input ref="fileInput" type="file" multiple class="hidden-input" @change="onFilesPicked" />
              </div>
            </div>
          </template>

          <el-form :inline="true" @submit.prevent>
            <el-form-item label="包名">
              <el-input v-model="pkgQuery.name" placeholder="按名称过滤" clearable @keyup.enter="loadPackages" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="loadPackages" v-if="auth.hasPerm('transfer:package:list')">查询</el-button>
              <el-button @click="resetPkgQuery">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table :data="pkgRows" v-loading="pkgLoading" border>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="name" label="包名" min-width="180" show-overflow-tooltip />
            <el-table-column prop="file_count" label="文件数" width="90" />
            <el-table-column label="大小" width="120">
              <template #default="{ row }">{{ formatSize(row.total_size) }}</template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" min-width="165" show-overflow-tooltip />
            <el-table-column label="操作" width="170">
              <template #default="{ row }">
                <el-button size="small" @click="openPackageDetail(row)" v-if="auth.hasPerm('transfer:package:list')">详情</el-button>
                <el-popconfirm
                  title="确定删除该包吗？被任务引用的包不可删除"
                  @confirm="handleDeletePackage(row)"
                  v-if="auth.hasPerm('transfer:package:del')"
                >
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
            :total="pkgTotal"
            :current-page="pkgQuery.page"
            :page-size="pkgQuery.size"
            :page-sizes="[10, 20, 50]"
            @current-change="onPkgPageChange"
            @size-change="onPkgSizeChange"
          />
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="任务列表" name="tasks" v-if="auth.hasPerm('transfer:task:list')">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>分发任务</span>
              <el-button type="primary" @click="showCreateDialog" v-if="auth.hasPerm('transfer:task:run')">新建任务</el-button>
            </div>
          </template>

          <el-form :inline="true" @submit.prevent>
            <el-form-item label="任务编号">
              <el-input v-model="query.task_no" placeholder="按编号过滤" clearable @keyup.enter="handleSearch" />
            </el-form-item>
            <el-form-item label="模式">
              <el-select v-model="query.mode" placeholder="全部" clearable style="width: 120px">
                <el-option label="push" value="push" />
                <el-option label="pull" value="pull" />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="query.status" placeholder="全部" clearable style="width: 160px">
                <el-option v-for="s in TASK_STATUSES" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="handleSearch" v-if="auth.hasPerm('transfer:task:list')">查询</el-button>
              <el-button @click="handleReset">重置</el-button>
            </el-form-item>
          </el-form>

          <el-table :data="rows" v-loading="loading" border>
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="task_no" label="任务编号" min-width="150" show-overflow-tooltip />
            <el-table-column label="模式" width="80">
              <template #default="{ row }">{{ row.mode === 'push' ? '分发' : '拉取' }}</template>
            </el-table-column>
            <el-table-column prop="target_path" label="目标路径" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="目标主机数" width="110">
              <template #default="{ row }">{{ hostCount(row.host_ids) }}</template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" min-width="165" show-overflow-tooltip />
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button size="small" @click="openDetail(row)" v-if="auth.hasPerm('transfer:task:list')">详情</el-button>
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
      </el-tab-pane>

      <el-tab-pane
        label="传输日志"
        name="logs"
        v-if="auth.hasPerm('transfer:task:log') && !auth.hasPerm('transfer:task:list')"
      >
        <el-card>
          <template #header>
            <div class="card-header">
              <span>我的分发任务日志</span>
            </div>
          </template>

          <el-alert
            v-if="!myTasksLoading && myTaskRows.length === 0"
            type="info"
            :closable="false"
            title="暂无任务日志"
            description="当前用户名下暂无已创建的分发任务。"
          />
          <el-table :data="myTaskRows" v-loading="myTasksLoading" border size="small">
            <el-table-column prop="task_no" label="任务编号" min-width="150" show-overflow-tooltip />
            <el-table-column label="模式" width="80">
              <template #default="{ row }">{{ row.mode === 'push' ? '分发' : '拉取' }}</template>
            </el-table-column>
            <el-table-column prop="target_path" label="目标路径" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="目标主机" min-width="220">
              <template #default="{ row }">
                <template v-for="hid in hostIds(row)" :key="hid">
                  <el-button size="small" class="host-log-btn" @click="openLogFromTask(row, hid)">
                    #{{ hid }} 日志
                  </el-button>
                </template>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="createVisible" title="新建分发任务" width="640px">
      <el-form :model="createForm" label-width="110px" ref="createFormRef" :rules="createRules">
        <el-form-item label="模式" prop="mode">
          <el-radio-group v-model="createForm.mode">
            <el-radio value="push">push（推送）</el-radio>
            <el-radio value="pull">pull（拉取）</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="createForm.mode === 'push'">
          <el-form-item label="文件包" prop="package_id">
            <el-select v-model="createForm.package_id" filterable placeholder="请选择文件包" style="width: 100%" v-loading="pkgOptionsLoading" @visible-change="loadPackageOptions">
              <el-option v-for="p in pkgOptions" :key="p.id" :label="`${p.name} (${p.file_count} 文件 / ${formatSize(p.total_size)})`" :value="p.id" />
            </el-select>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="源路径" prop="source_host_path">
            <el-input v-model="createForm.source_host_path" placeholder="如 /var/lib/lark-agent/outbox/xxx，需在白名单内" />
          </el-form-item>
        </template>

        <el-form-item label="目标路径" prop="target_path">
          <el-input v-model="createForm.target_path" placeholder="目标主机上的路径" />
        </el-form-item>
        <el-form-item label="目标主机" prop="host_ids">
          <el-select
            v-model="createForm.host_ids"
            multiple
            filterable
            placeholder="请选择目标主机（可多选）"
            style="width: 100%"
            v-loading="hostsLoading"
          >
            <el-option
              v-for="h in hostOptions"
              :key="h.id"
              :label="`${h.hostname} (${h.ip})`"
              :value="h.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="覆盖">
          <el-switch v-model="createForm.overwrite" active-text="覆盖已存在文件" />
        </el-form-item>
        <el-form-item label="校验">
          <el-switch v-model="createForm.verify" active-text="逐主机 sha256 校验" />
        </el-form-item>
        <el-form-item label="限速(Mbps)">
          <el-input-number v-model="createForm.limit_mbps" :min="1" :max="10000" placeholder="0/空=不限速" />
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
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(detail.status)">{{ statusLabel(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="模式">{{ detail.mode === 'push' ? 'push（推送）' : 'pull（拉取）' }}</el-descriptions-item>
          <el-descriptions-item label="包ID">{{ detail.package_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="目标路径">{{ detail.target_path }}</el-descriptions-item>
          <el-descriptions-item label="覆盖/校验">{{ detail.overwrite === 1 ? '覆盖' : '不覆盖' }} / {{ detail.verify === 1 ? '校验' : '不校验' }}</el-descriptions-item>
          <el-descriptions-item label="限速">{{ detail.limit_mbps ? `${detail.limit_mbps} Mbps` : '不限' }}</el-descriptions-item>
          <el-descriptions-item label="源主机">{{ detail.source_host_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="源路径">{{ detail.source_host_path ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ detail.started_at ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ detail.finished_at ?? '-' }}</el-descriptions-item>
        </el-descriptions>

        <h4 class="section-title">传输统计</h4>
        <div v-if="detail.stats" class="stats-row">
          <el-tag type="info" size="small">总 {{ detail.stats.total }}</el-tag>
          <el-tag type="info" size="small">等待 {{ detail.stats.pending }}</el-tag>
          <el-tag type="primary" size="small">传输中 {{ detail.stats.transferring }}</el-tag>
          <el-tag type="primary" size="small">校验中 {{ detail.stats.verifying }}</el-tag>
          <el-tag type="warning" size="small">校验失败 {{ detail.stats.verify_failed }}</el-tag>
          <el-tag type="success" size="small">成功 {{ detail.stats.success }}</el-tag>
          <el-tag type="danger" size="small">失败 {{ detail.stats.failed }}</el-tag>
        </div>

        <h4 class="section-title">目标主机（点击「日志」查看实时传输日志）</h4>
        <el-table :data="detail.hosts" border size="small">
          <el-table-column prop="id" label="transfer_host_id" width="130" />
          <el-table-column prop="hostname" label="主机名" min-width="120" show-overflow-tooltip />
          <el-table-column prop="ip" label="IP" min-width="110" />
          <el-table-column prop="channel" label="通道" width="80" />
          <el-table-column label="状态" width="110">
            <template #default="{ row }">
              <el-tag :type="hostStatusTagType(row.status)" size="small">{{ hostStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="current_offset" label="游标" width="90" />
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button size="small" @click="openLogViewer(row)" v-if="auth.hasPerm('transfer:task:log')">日志</el-button>
            </template>
          </el-table-column>
        </el-table>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="logVisible" :title="`实时日志 - ${logHost?.hostname ?? ''} (transfer_host_id=${logHost?.id ?? ''})`" width="760px" @closed="stopLogViewer">
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

    <el-dialog v-model="pkgDetailVisible" :title="`包详情 - ${pkgDetail?.name ?? ''}`" width="640px">
      <div v-loading="pkgDetailLoading">
        <template v-if="pkgDetail">
        <el-descriptions :column="2" border size="small" class="block-gap">
          <el-descriptions-item label="ID">{{ pkgDetail.id }}</el-descriptions-item>
          <el-descriptions-item label="包名">{{ pkgDetail.name }}</el-descriptions-item>
          <el-descriptions-item label="文件数">{{ pkgDetail.file_count }}</el-descriptions-item>
          <el-descriptions-item label="总大小">{{ formatSize(pkgDetail.total_size) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间" :span="2">{{ pkgDetail.created_at }}</el-descriptions-item>
        </el-descriptions>
        <el-table :data="pkgDetail.items" border size="small" class="block-gap">
          <el-table-column prop="path" label="相对路径" min-width="220" show-overflow-tooltip />
          <el-table-column label="大小" width="110">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column prop="sha256" label="sha256" min-width="260" show-overflow-tooltip />
        </el-table>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  uploadPackage,
  getPackages,
  getPackage,
  deletePackage,
  createTransferTask,
  getTransferTasks,
  getMyTransferTasks,
  getTransferTask,
  stopTransferTask,
  retryTransferHost,
} from '../../api/transfer'
import { getHosts } from '../../api/assets'
import { useTransferRealtimeLog } from '../../composables/useTransferRealtimeLog'
import type {
  TransferPackageOut,
  TransferTaskOut,
  TransferTaskDetail,
  TransferTaskStatus,
  HostOut,
} from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()

const TASK_STATUSES = [
  { value: 'processing', label: '处理中' },
  { value: 'success', label: '成功' },
  { value: 'partial', label: '部分成功' },
  { value: 'failed', label: '失败' },
  { value: 'canceled', label: '已取消' },
]

const STATUS_TAG_TYPES: Record<string, string> = {
  processing: 'primary',
  success: 'success',
  partial: 'warning',
  failed: 'danger',
  canceled: 'info',
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
    pulling: '拉取中',
    transferring: '传输中',
    verifying: '校验中',
    success: '成功',
    failed: '失败',
    verify_failed: '校验失败',
    degraded: '降级',
    canceled: '取消',
  }
  return map[status] ?? status
}

function hostStatusTagType(status: string): string {
  const map: Record<string, string> = {
    pending: 'info',
    pulling: 'primary',
    transferring: 'primary',
    verifying: 'primary',
    success: 'success',
    failed: 'danger',
    verify_failed: 'warning',
    degraded: 'info',
    canceled: 'info',
  }
  return map[status] ?? 'info'
}

function hostCount(hostIds: Record<string, unknown> | null): number {
  if (!hostIds || !Array.isArray(hostIds.ids)) return 0
  return hostIds.ids.length
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(2)} KB`
  return `${bytes} B`
}

function canStop(task: TransferTaskOut): boolean {
  return auth.hasPerm('transfer:task:stop') && ['processing'].includes(task.status)
}

function canRetry(task: TransferTaskOut): boolean {
  return auth.hasPerm('transfer:task:retry') && ['failed', 'canceled'].includes(task.status)
}

const activeTab = ref('packages')

// ---------------------------------------------------------------- packages
const pkgRows = ref<TransferPackageOut[]>([])
const pkgTotal = ref(0)
const pkgLoading = ref(false)
const pkgQuery = reactive({ name: '', page: 1, size: 10 })
const fileInput = ref<HTMLInputElement>()

async function loadPackages() {
  pkgLoading.value = true
  try {
    const page = await getPackages({
      name: pkgQuery.name || undefined,
      page: pkgQuery.page,
      size: pkgQuery.size,
    })
    pkgRows.value = page.list
    pkgTotal.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    pkgLoading.value = false
  }
}

function resetPkgQuery() {
  pkgQuery.name = ''
  pkgQuery.page = 1
  loadPackages()
}

function onPkgPageChange(page: number) {
  pkgQuery.page = page
  loadPackages()
}

function onPkgSizeChange(size: number) {
  pkgQuery.size = size
  pkgQuery.page = 1
  loadPackages()
}

function pickFiles() {
  fileInput.value?.click()
}

const uploading = ref(false)
async function onFilesPicked(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (files.length === 0) return
  uploading.value = true
  try {
    const result = await uploadPackage(files)
    ElMessage.success(`上传成功：包 #${result.package_id}，共 ${result.items.length} 个文件`)
    loadPackages()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    uploading.value = false
  }
}

const pkgDetailVisible = ref(false)
const pkgDetailLoading = ref(false)
const pkgDetail = ref<TransferPackageOut & { items: { path: string; size: number; sha256: string }[] } | null>(null)

async function openPackageDetail(row: TransferPackageOut) {
  pkgDetailVisible.value = true
  pkgDetailLoading.value = true
  try {
    pkgDetail.value = await getPackage(row.id)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    pkgDetailLoading.value = false
  }
}

async function handleDeletePackage(row: TransferPackageOut) {
  try {
    await deletePackage(row.id)
    ElMessage.success('包已删除')
    loadPackages()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

// ---------------------------------------------------------------- tasks
const rows = ref<TransferTaskOut[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ task_no: '', mode: '', status: '', page: 1, size: 10 })

async function loadRows() {
  loading.value = true
  try {
    const page = await getTransferTasks({
      task_no: query.task_no || undefined,
      mode: (query.mode || undefined) as 'push' | 'pull' | undefined,
      status: (query.status || undefined) as TransferTaskStatus | undefined,
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
  query.mode = ''
  query.status = ''
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

async function handleStop(task: TransferTaskOut) {
  try {
    await stopTransferTask(task.id)
    ElMessage.success('停止指令已下发')
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function handleRetry(task: TransferTaskOut) {
  try {
    const fresh = await getTransferTask(task.id)
    const retryable = fresh.hosts.filter((h) => ['failed', 'verify_failed', 'degraded'].includes(h.status))
    if (retryable.length === 0) {
      ElMessage.warning('没有可重试的主机')
      return
    }
    for (const h of retryable) {
      await retryTransferHost(task.id, h.id)
    }
    ElMessage.success(`已发起 ${retryable.length} 台主机重试`)
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const createVisible = ref(false)
const createFormRef = ref()
const submitLoading = ref(false)
const createForm = reactive({
  mode: 'push' as 'push' | 'pull',
  package_id: undefined as number | undefined,
  source_host_path: '',
  target_path: '',
  host_ids: [] as number[],
  overwrite: false,
  verify: true,
  limit_mbps: undefined as number | undefined,
})
const createRules = {
  mode: [{ required: true, message: '请选择模式', trigger: 'change' }],
  package_id: [{ required: true, message: '请选择文件包', trigger: 'change' }],
  source_host_path: [{ required: true, message: '请输入源路径', trigger: 'blur' }],
  target_path: [{ required: true, message: '请输入目标路径', trigger: 'blur' }],
  host_ids: [{ required: true, type: 'array', min: 1, message: '请至少选择一台目标主机', trigger: 'change' }],
}

const hostOptions = ref<HostOut[]>([])
const hostsLoading = ref(false)
const pkgOptions = ref<TransferPackageOut[]>([])
const pkgOptionsLoading = ref(false)

async function loadPackageOptions(visible: boolean) {
  if (!visible || pkgOptions.value.length > 0) return
  pkgOptionsLoading.value = true
  try {
    const page = await getPackages({ page: 1, size: 100 })
    pkgOptions.value = page.list
  } catch {
    pkgOptions.value = []
  } finally {
    pkgOptionsLoading.value = false
  }
}

async function showCreateDialog() {
  Object.assign(createForm, {
    mode: 'push',
    package_id: undefined,
    source_host_path: '',
    target_path: '',
    host_ids: [],
    overwrite: false,
    verify: true,
    limit_mbps: undefined,
  })
  createVisible.value = true
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
    await createTransferTask({
      mode: createForm.mode,
      package_id: createForm.mode === 'push' ? createForm.package_id : undefined,
      source_host_path: createForm.mode === 'pull' ? createForm.source_host_path : undefined,
      target_path: createForm.target_path,
      host_ids: createForm.host_ids,
      overwrite: createForm.overwrite ? 1 : 0,
      verify: createForm.verify ? 1 : 0,
      limit_mbps: createForm.limit_mbps || undefined,
    })
    ElMessage.success('任务已创建')
    createVisible.value = false
    activeTab.value = 'tasks'
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<TransferTaskDetail | null>(null)

async function openDetail(row: TransferTaskOut) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getTransferTask(row.id)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    detailLoading.value = false
  }
}

const logVisible = ref(false)
const logHost = ref<{ id: number; hostname: string } | null>(null)
const logContainer = ref<HTMLElement>()
let logSession: ReturnType<typeof useTransferRealtimeLog> | null = null
const sessionVersion = ref(0)
const logLines = computed(() => {
  void sessionVersion.value
  return logSession?.lines.value ?? []
})
const logConnected = computed(() => {
  void sessionVersion.value
  return logSession?.connected.value ?? false
})

function openLogViewer(host: { id: number; hostname: string }, taskId?: number) {
  const tid = taskId ?? detail.value?.id
  if (!tid) return
  stopLogViewer()
  logHost.value = host
  logVisible.value = true
  logSession = useTransferRealtimeLog({
    taskId: tid,
    transferHostId: host.id,
    onStatus: (status) => {
      ElMessage.info(`主机状态：${status}`)
    },
  })
  sessionVersion.value += 1
  void nextTick(() => scrollToBottom())
  logSession.start()
}

const myTaskRows = ref<TransferTaskOut[]>([])
const myTasksLoading = ref(false)
const myTasksLoaded = ref(false)

function hostIds(task: TransferTaskOut): number[] {
  if (!task.host_ids || !Array.isArray(task.host_ids.ids)) return []
  return (task.host_ids.ids as number[])
}

async function loadMyTasks() {
  myTasksLoading.value = true
  try {
    const page = await getMyTransferTasks({ page: 1, size: 100 })
    myTaskRows.value = page.list
    myTasksLoaded.value = true
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    myTasksLoading.value = false
  }
}

function openLogFromTask(task: TransferTaskOut, transferHostId: number) {
  openLogViewer(
    { id: transferHostId, hostname: `任务 ${task.task_no} · 主机 #${transferHostId}` },
    task.id,
  )
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

watch(
  activeTab,
  (tab) => {
    if (tab === 'packages' && pkgRows.value.length === 0) loadPackages()
    if (tab === 'tasks' && rows.value.length === 0) loadRows()
    if (tab === 'logs' && !myTasksLoaded.value) loadMyTasks()
  },
  { immediate: true },
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
.hidden-input {
  display: none;
}
.pagination {
  margin-top: 12px;
  justify-content: flex-end;
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