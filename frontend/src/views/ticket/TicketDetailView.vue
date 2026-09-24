<template>
  <div class="page" v-loading="loading">
    <el-card>
      <template #header>
        <div class="toolbar">
          <div class="left">
            <el-button @click="goBack">返回</el-button>
            <span class="title">工单 {{ ticket?.ticket_no }}</span>
            <el-tag v-if="ticket" :type="statusTag(ticket.status)">{{ statusLabel(ticket.status) }}</el-tag>
          </div>
          <div class="actions" v-if="ticket">
            <el-button v-if="canEdit" v-perm="'ticket:edit'" @click="openEdit">编辑</el-button>
            <el-button v-if="show('assign')" v-perm="'ticket:assign'" type="primary" @click="openAssign">指派</el-button>
            <el-button v-if="show('accept')" v-perm="'ticket:accept'" type="primary" @click="doAccept">受理</el-button>
            <el-button v-if="show('process')" v-perm="'ticket:process'" type="primary" @click="doProcess">开始处理</el-button>
            <el-button v-if="show('done')" v-perm="'ticket:done'" type="success" @click="openDone">完成</el-button>
            <el-button v-if="show('close')" v-perm="'ticket:close'" type="success" @click="doClose">关闭</el-button>
            <el-button v-if="show('reopen')" v-perm="'ticket:reopen'" @click="doReopen">重新打开</el-button>
            <el-button v-if="show('cancel')" v-perm="'ticket:cancel'" type="danger" @click="doCancel">取消</el-button>
          </div>
        </div>
      </template>

      <template v-if="ticket">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="工单编号">{{ ticket.ticket_no }}</el-descriptions-item>
          <el-descriptions-item label="ID">{{ ticket.id }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ ticket.version }}</el-descriptions-item>
          <el-descriptions-item label="标题" :span="3">{{ ticket.title }}</el-descriptions-item>
          <el-descriptions-item label="分类">{{ categoryLabel(ticket.category) }}</el-descriptions-item>
          <el-descriptions-item label="优先级">
            <el-tag :type="priorityTag(ticket.priority)" size="small">{{ priorityLabel(ticket.priority) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="申请人">{{ ticket.requester_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="负责人">{{ ticket.assignee_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="截止时间">{{ formatTime(ticket.sla_due_at) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(ticket.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="解决时间">{{ formatTime(ticket.resolved_at) }}</el-descriptions-item>
          <el-descriptions-item label="关闭时间">{{ formatTime(ticket.closed_at) }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="3">{{ ticket.description || '-' }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">关联对象</el-divider>
        <div class="refs">
          <el-tag v-for="r in ticket.refs" :key="r.id" class="ref-tag" closable @close="noop">
            {{ refTypeLabel(r.ref_type) }} #{{ r.ref_id }}
          </el-tag>
          <el-button v-perm="'ticket:ref'" size="small" @click="openRef">关联</el-button>
        </div>

        <el-divider content-position="left">附件</el-divider>
        <el-table :data="ticket.attachments" border size="small">
          <el-table-column prop="filename" label="文件名" min-width="200" />
          <el-table-column prop="size" label="大小" width="110">
            <template #default="{ row }">{{ formatSize(row.size) }}</template>
          </el-table-column>
          <el-table-column label="上传时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
        <div class="upload">
          <input ref="fileInput" type="file" multiple style="display: none" @change="onFiles" />
          <el-button v-perm="'ticket:attachment'" size="small" :loading="uploading" @click="pickFiles">上传附件</el-button>
        </div>

        <el-divider content-position="left">评论</el-divider>
        <el-timeline>
          <el-timeline-item
            v-for="c in ticket.comments"
            :key="c.id"
            :timestamp="formatTime(c.created_at)"
          >
            <b>#{{ c.author_id ?? '-' }}</b>：{{ c.content }}
          </el-timeline-item>
        </el-timeline>
        <div class="comment">
          <el-input v-model="commentText" type="textarea" :rows="2" placeholder="输入评论" />
          <el-button v-perm="'ticket:comment'" type="primary" :loading="commenting" @click="onComment">发表</el-button>
        </div>
      </template>
    </el-card>

    <el-dialog v-model="editVisible" title="编辑工单" width="540px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="标题"><el-input v-model="editForm.title" :maxlength="256" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="editForm.category" style="width: 100%">
            <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="editForm.priority" style="width: 100%">
            <el-option v-for="p in priorityOptions" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-select
            v-model="editForm.assignee_id"
            clearable
            :disabled="!canAssign"
            :placeholder="canAssign ? '' : '无 ticket:assign 权限'"
            style="width: 100%"
          >
            <el-option v-for="u in users" :key="u.id" :label="`${u.real_name || u.username} (#${u.id})`" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker v-model="editForm.due_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="assignVisible" title="指派工单" width="420px">
      <el-form label-width="80px">
        <el-form-item label="负责人">
          <el-select v-model="assigneeId" style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="`${u.real_name || u.username} (#${u.id})`" :value="u.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onAssign">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="doneVisible" title="完成工单" width="460px">
      <el-form label-width="90px">
        <el-form-item label="处理说明">
          <el-input v-model="doneForm.remark" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="关联执行">
          <el-input-number v-model="doneForm.exec_task_id" :min="1" placeholder="执行任务 ID（可选）" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="doneVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onDone">完成</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="refVisible" title="关联对象" width="420px">
      <el-form label-width="80px">
        <el-form-item label="类型">
          <el-select v-model="refForm.ref_type" style="width: 100%">
            <el-option v-for="t in refTypeOptions" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="对象 ID">
          <el-input-number v-model="refForm.ref_id" :min="1" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="refVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onAddRef">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getTicket,
  updateTicket,
  assignTicket,
  acceptTicket,
  processTicket,
  doneTicket,
  closeTicket,
  reopenTicket,
  cancelTicket,
  addTicketComment,
  addTicketRef,
  uploadTicketAttachments,
} from '../../api/ticket'
import { listUsers } from '../../api/system'
import { useAuthStore } from '../../stores/auth'
import type { TicketDetail, TicketUpdate, UserOut } from '../../api/types'
import { extractError } from '../../api/http'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const canAssign = computed(() => auth.hasPerm('ticket:assign'))
const ticketId = Number(route.params.id)

const loading = ref(false)
const saving = ref(false)
const ticket = ref<TicketDetail | null>(null)

const categoryOptions = [
  { value: 'incident', label: '故障' },
  { value: 'change', label: '变更' },
  { value: 'request', label: '请求' },
  { value: 'other', label: '其他' },
]
const priorityOptions = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'urgent', label: '紧急' },
]
const statusOptions = [
  { value: 'create', label: '待指派' },
  { value: 'assign', label: '已指派' },
  { value: 'accept', label: '已受理' },
  { value: 'processing', label: '处理中' },
  { value: 'done', label: '已完成' },
  { value: 'close', label: '已关闭' },
  { value: 'cancel', label: '已取消' },
]
const refTypeOptions = [
  { value: 'exec_task', label: '执行任务' },
  { value: 'approval', label: '审批单' },
  { value: 'asset_host', label: '主机' },
  { value: 'schedule', label: '定时任务' },
  { value: 'kb_article', label: '知识文章' },
  { value: 'script', label: '脚本' },
]

function categoryLabel(v: string): string {
  return categoryOptions.find((o) => o.value === v)?.label ?? v
}
function priorityLabel(v: string): string {
  return priorityOptions.find((o) => o.value === v)?.label ?? v
}
function priorityTag(v: string): string {
  return v === 'urgent' ? 'danger' : v === 'high' ? 'warning' : v === 'low' ? 'info' : ''
}
function statusLabel(v: string): string {
  return statusOptions.find((o) => o.value === v)?.label ?? v
}
function statusTag(v: string): string {
  switch (v) {
    case 'done':
    case 'close':
      return 'success'
    case 'cancel':
      return 'info'
    case 'processing':
      return 'primary'
    default:
      return 'warning'
  }
}
function refTypeLabel(v: string): string {
  return refTypeOptions.find((o) => o.value === v)?.label ?? v
}
function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}
function formatSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}
function noop() {}

// action-keyed transitions (mirror backend TICKET_TRANSITIONS; ordering is not contract)
const TRANSITIONS: Record<string, string[]> = {
  assign: ['create', 'assign'],
  accept: ['assign'],
  process: ['accept'],
  done: ['processing'],
  close: ['done'],
  reopen: ['done', 'close'],
  cancel: ['create', 'assign', 'accept', 'processing'],
}
function show(action: string): boolean {
  return !!ticket.value && TRANSITIONS[action].includes(ticket.value.status)
}
const canEdit = computed(() => !!ticket.value && ['create', 'assign'].includes(ticket.value.status))

async function load() {
  loading.value = true
  try {
    ticket.value = await getTicket(ticketId)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push('/tickets')
}

async function run(fn: () => Promise<unknown>, okMsg: string) {
  saving.value = true
  try {
    await fn()
    ElMessage.success(okMsg)
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

const doAccept = () => run(() => acceptTicket(ticketId), '已受理')
const doProcess = () => run(() => processTicket(ticketId), '已开始处理')
const doClose = () => run(() => closeTicket(ticketId), '已关闭')
const doReopen = () => run(() => reopenTicket(ticketId), '已重新打开')
const doCancel = () => run(() => cancelTicket(ticketId), '已取消')

// ---- edit
const editVisible = ref(false)
const editForm = reactive<TicketUpdate>({
  title: '',
  category: 'incident',
  priority: 'medium',
  description: '',
  assignee_id: null,
  due_at: null,
})
const users = ref<UserOut[]>([])

function openEdit() {
  if (!ticket.value) return
  editForm.title = ticket.value.title
  editForm.category = ticket.value.category as TicketUpdate['category']
  editForm.priority = ticket.value.priority as TicketUpdate['priority']
  editForm.description = ticket.value.description
  editForm.assignee_id = ticket.value.assignee_id
  editForm.due_at = ticket.value.sla_due_at
  editVisible.value = true
}

async function onSaveEdit() {
  await run(async () => {
    if (!editForm.title) throw new Error('请输入标题')
    await updateTicket(ticketId, { ...editForm, due_at: editForm.due_at || null })
    editVisible.value = false
  }, '已保存')
}

// ---- assign
const assignVisible = ref(false)
const assigneeId = ref<number | null>(null)

function openAssign() {
  assigneeId.value = ticket.value?.assignee_id ?? null
  assignVisible.value = true
}

async function onAssign() {
  if (!assigneeId.value) {
    ElMessage.warning('请选择负责人')
    return
  }
  await run(async () => {
    await assignTicket(ticketId, { assignee_id: assigneeId.value as number })
    assignVisible.value = false
  }, '已指派')
}

// ---- done
const doneVisible = ref(false)
const doneForm = reactive<{ remark: string; exec_task_id: number | null }>({ remark: '', exec_task_id: null })

function openDone() {
  doneForm.remark = ''
  doneForm.exec_task_id = null
  doneVisible.value = true
}

async function onDone() {
  await run(async () => {
    await doneTicket(ticketId, { remark: doneForm.remark, exec_task_id: doneForm.exec_task_id || null })
    doneVisible.value = false
  }, '已完成')
}

// ---- ref
const refVisible = ref(false)
const refForm = reactive({ ref_type: 'exec_task', ref_id: 1 })

function openRef() {
  refForm.ref_type = 'exec_task'
  refForm.ref_id = 1
  refVisible.value = true
}

async function onAddRef() {
  await run(async () => {
    await addTicketRef(ticketId, { ref_type: refForm.ref_type, ref_id: refForm.ref_id })
    refVisible.value = false
  }, '已关联')
}

// ---- comment
const commentText = ref('')
const commenting = ref(false)

async function onComment() {
  if (!commentText.value.trim()) return
  commenting.value = true
  try {
    await addTicketComment(ticketId, commentText.value)
    commentText.value = ''
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    commenting.value = false
  }
}

// ---- attachments
const uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

function pickFiles() {
  fileInput.value?.click()
}

async function onFiles(ev: Event) {
  const input = ev.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (!files.length) return
  uploading.value = true
  try {
    await uploadTicketAttachments(ticketId, files)
    ElMessage.success('已上传')
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function loadUsers() {
  try {
    const page = await listUsers({ page: 1, size: 100 })
    users.value = page.list
  } catch {
    users.value = []
  }
}

onMounted(() => {
  load()
  loadUsers()
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
.refs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.upload {
  margin-top: 8px;
}
.comment {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-top: 8px;
}
</style>
