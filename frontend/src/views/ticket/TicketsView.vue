<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">工单管理</span>
          <el-button type="primary" v-perm="'ticket:create'" @click="openCreate">新建工单</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load">
        <el-form-item label="分类">
          <el-select v-model="query.category" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="query.priority" clearable placeholder="全部" style="width: 120px">
            <el-option v-for="p in priorityOptions" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border @row-click="openDetail">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
        <el-table-column label="分类" width="90">
          <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
        </el-table-column>
        <el-table-column label="优先级" width="90">
          <template #default="{ row }">
            <el-tag :type="priorityTag(row.priority)" size="small">{{ priorityLabel(row.priority) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="负责人" width="90">
          <template #default="{ row }">{{ row.assignee_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click.stop="openDetail(row)">详情</el-button>
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

    <el-dialog v-model="createVisible" title="新建工单" width="560px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="form.title" :maxlength="256" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="c in categoryOptions" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="form.priority" style="width: 100%">
            <el-option v-for="p in priorityOptions" :key="p.value" :label="p.label" :value="p.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="form.assignee_id" clearable placeholder="可不指定" style="width: 100%">
            <el-option v-for="u in users" :key="u.id" :label="`${u.real_name || u.username} (#${u.id})`" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker v-model="form.due_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width: 100%" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="onCreate">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listTickets, createTicket } from '../../api/ticket'
import { listUsers } from '../../api/system'
import type { TicketOut, TicketQuery, TicketCreate, TicketCategory, TicketPriority, UserOut } from '../../api/types'
import { extractError } from '../../api/http'

const router = useRouter()
const loading = ref(false)
const rows = ref<TicketOut[]>([])
const total = ref(0)
const query = reactive<TicketQuery>({ page: 1, size: 10 })

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
function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

async function load() {
  loading.value = true
  try {
    const page = await listTickets({ ...query })
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.category = undefined
  query.status = undefined
  query.priority = undefined
  query.page = 1
  load()
}

function openDetail(row: TicketOut) {
  router.push(`/tickets/${row.id}`)
}

const createVisible = ref(false)
const creating = ref(false)
const form = reactive<TicketCreate>({
  title: '',
  category: 'incident',
  priority: 'medium',
  description: '',
  assignee_id: null,
  due_at: null,
})
const users = ref<UserOut[]>([])

function openCreate() {
  form.title = ''
  form.category = 'incident'
  form.priority = 'medium'
  form.description = ''
  form.assignee_id = null
  form.due_at = null
  createVisible.value = true
}

async function onCreate() {
  if (!form.title.trim()) {
    ElMessage.warning('请输入标题')
    return
  }
  creating.value = true
  try {
    const payload: TicketCreate = {
      title: form.title,
      category: form.category as TicketCategory,
      priority: form.priority as TicketPriority,
      description: form.description,
      assignee_id: form.assignee_id ?? null,
      due_at: form.due_at || null,
    }
    await createTicket(payload)
    ElMessage.success('已创建')
    createVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    creating.value = false
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
}
.title {
  font-weight: 600;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
