<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">Web 终端</span>
          <el-button type="primary" v-perm="'terminal:create'" @click="openCreate">连接终端</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load">
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option label="活动中" value="active" />
            <el-option label="已关闭" value="closed" />
            <el-option label="等待审批" value="pending" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="session_no" label="会话号" min-width="160" />
        <el-table-column prop="host_id" label="主机ID" width="80" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="敏感" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.sensitive === 1" type="danger" size="small">敏感</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="duration_sec" label="时长" width="90">
          <template #default="{ row }">{{ row.duration_sec }}s</template>
        </el-table-column>
        <el-table-column prop="bytes_out" label="输出字节" width="100" />
        <el-table-column prop="started_at" label="开始时间" width="170">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="primary"
              v-perm="'terminal:view'"
              @click="openConsole(row)"
            >
              控制台
            </el-button>
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="warning"
              v-perm="'terminal:close'"
              @click="onClose(row)"
            >
              关闭
            </el-button>
            <el-button
              v-if="row.status === 'closed'"
              size="small"
              v-perm="'terminal:replay'"
              @click="openReplay(row)"
            >
              回放
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

    <el-dialog v-model="createVisible" title="连接终端" width="480px">
      <el-form :model="createForm" label-width="80px">
        <el-form-item label="主机">
          <el-select v-model="createForm.host_id" filterable style="width: 100%" placeholder="选择主机">
            <el-option v-for="h in hostOptions" :key="h.id" :label="`${h.hostname} (${h.ip})`" :value="h.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="createForm.reason" type="textarea" :rows="2" placeholder="操作原因（敏感主机必填）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">连接</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="replayVisible" title="会话回放" width="720px">
      <div class="replay-block" v-loading="replayLoading">
        <pre v-if="replayText" class="replay-pre">{{ replayText }}</pre>
        <el-empty v-else description="暂无录制内容" />
        <div v-if="replayHasMore" class="replay-more">
          <el-button size="small" @click="loadMoreReplay">加载更多</el-button>
        </div>
      </div>
    </el-dialog>

    <el-dialog
      v-model="consoleVisible"
      :title="`终端控制台 - ${consoleSession?.session_no ?? ''}`"
      width="780px"
      @closed="stopConsole"
    >
      <div class="console-toolbar">
        <el-tag :type="consoleConnected ? 'success' : 'info'" size="small">
          {{ consoleConnected ? '已连接' : '未连接' }}
        </el-tag>
        <span class="console-offset">已接收 {{ consoleBuffer.length }} 字符</span>
      </div>
      <div ref="consoleContainer" class="console-block">
        <pre class="console-pre">{{ consoleBuffer || '' }}</pre>
      </div>
      <el-input
        v-model="consoleInput"
        class="console-input"
        placeholder="输入命令，回车发送"
        :disabled="!consoleConnected"
        @keydown.enter.prevent="sendConsoleInput"
      >
        <template #append>
          <el-button type="primary" :disabled="!consoleConnected" @click="sendConsoleInput">发送</el-button>
        </template>
      </el-input>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getHosts } from '../../api/assets'
import {
  closeTerminal,
  createTerminal,
  getRecording,
  listTerminals,
} from '../../api/terminals'
import type { HostOut, TerminalOut, TerminalQuery } from '../../api/types'
import { extractError } from '../../api/http'
import { useTerminalConsole } from '../../composables/useTerminalConsole'

const loading = ref(false)
const rows = ref<TerminalOut[]>([])
const total = ref(0)
const query = reactive<TerminalQuery>({ page: 1, size: 10 })

const hostOptions = ref<HostOut[]>([])

function statusLabel(s: string): string {
  switch (s) {
    case 'active':
      return '活动中'
    case 'closed':
      return '已关闭'
    case 'pending':
      return '等待审批'
    default:
      return s
  }
}

function statusTag(s: string): string {
  switch (s) {
    case 'active':
      return 'success'
    case 'closed':
      return 'info'
    case 'pending':
      return 'warning'
    default:
      return 'info'
  }
}

function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

async function load() {
  loading.value = true
  try {
    const page = await listTerminals(query)
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.status = undefined
  query.page = 1
  load()
}

const createVisible = ref(false)
const creating = ref(false)
const createForm = reactive<{ host_id: number | null; reason: string }>({ host_id: null, reason: '' })

async function openCreate() {
  createForm.host_id = null
  createForm.reason = ''
  createVisible.value = true
  if (hostOptions.value.length === 0) {
    try {
      const page = await getHosts({ page: 1, size: 100 })
      hostOptions.value = page.list
    } catch {
      hostOptions.value = []
    }
  }
}

async function onCreate() {
  if (createForm.host_id == null) {
    ElMessage.warning('请选择主机')
    return
  }
  creating.value = true
  try {
    const result = await createTerminal({
      host_id: createForm.host_id,
      reason: createForm.reason,
    })
    ElMessage.success(`会话创建成功（${result.session_no}）`)
    if (result.status === 'pending') {
      ElMessage.info('该终端为敏感主机，需审批通过后使用')
    }
    createVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    creating.value = false
  }
}

async function onClose(row: TerminalOut) {
  try {
    await ElMessageBox.confirm(`确定关闭会话「${row.session_no}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await closeTerminal(row.id)
    ElMessage.success('已关闭')
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const replayVisible = ref(false)
const replayLoading = ref(false)
const replayText = ref('')
const replayOffset = ref(0)
const replayHasMore = ref(false)
const replaySessionId = ref<number | null>(null)

const consoleVisible = ref(false)
const consoleSession = ref<TerminalOut | null>(null)
const consoleInput = ref('')
const consoleContainer = ref<HTMLElement>()
let consoleSessionRef: ReturnType<typeof useTerminalConsole> | null = null
const sessionVersion = ref(0)
const consoleBuffer = computed(() => {
  void sessionVersion.value
  return consoleSessionRef?.buffer.value ?? ''
})
const consoleConnected = computed(() => {
  void sessionVersion.value
  return consoleSessionRef?.connected.value ?? false
})

function openConsole(row: TerminalOut) {
  stopConsole()
  consoleSession.value = row
  consoleInput.value = ''
  consoleVisible.value = true
  consoleSessionRef = useTerminalConsole({
    sessionId: row.id,
    cols: 120,
    rows: 40,
    onStatus: (status) => {
      ElMessage.info(`会话状态：${status}`)
      if (status === 'closed') stopConsole()
    },
  })
  sessionVersion.value += 1
  void nextTick(() => scrollConsoleToBottom())
  consoleSessionRef.start()
}

function stopConsole() {
  consoleSessionRef?.stop()
  consoleSessionRef = null
  sessionVersion.value += 1
  consoleSession.value = null
}

function sendConsoleInput() {
  const text = consoleInput.value
  if (!text || !consoleSessionRef?.connected.value) return
  consoleInput.value = ''
  consoleSessionRef.sendInput(text + '\r')
  void nextTick(() => scrollConsoleToBottom())
}

function scrollConsoleToBottom() {
  const el = consoleContainer.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => consoleSessionRef?.buffer.value.length ?? 0,
  () => {
    void nextTick(() => scrollConsoleToBottom())
  },
)

async function openReplay(row: TerminalOut) {
  replaySessionId.value = row.id
  replayText.value = ''
  replayOffset.value = 0
  replayHasMore.value = false
  replayVisible.value = true
  await loadReplay()
}

async function loadReplay() {
  if (replaySessionId.value == null) return
  replayLoading.value = true
  try {
    const rec = await getRecording(replaySessionId.value, replayOffset.value, 100)
    for (const chunk of rec.chunks) {
      replayText.value += chunk.data
    }
    replayOffset.value = rec.after_offset
    replayHasMore.value = rec.has_more
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    replayLoading.value = false
  }
}

async function loadMoreReplay() {
  await loadReplay()
}

onMounted(load)

onBeforeUnmount(() => {
  stopConsole()
})
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
.replay-block {
  max-height: 60vh;
  overflow: auto;
}
.replay-pre {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px;
  border-radius: 4px;
  font-family: Menlo, Consolas, monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
}
.replay-more {
  text-align: center;
  margin-top: 8px;
}
.console-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.console-offset {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.console-block {
  height: 360px;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 4px;
  padding: 8px 12px;
  margin-bottom: 8px;
}
.console-pre {
  color: #d4d4d4;
  font-family: Menlo, Consolas, monospace;
  font-size: 13px;
  line-height: 20px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
