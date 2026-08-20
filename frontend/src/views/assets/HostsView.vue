<template>
  <div class="hosts-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>主机管理</span>
          <div class="actions">
            <el-button type="primary" @click="showCreateDialog" v-if="auth.hasPerm('asset:host:create')">新增主机</el-button>
            <el-button @click="showImportDialog" v-if="auth.hasPerm('asset:host:create')">导入 CSV</el-button>
            <el-button @click="handleExport" v-if="auth.hasPerm('asset:host:list')">导出 CSV</el-button>
          </div>
        </div>
      </template>

      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="主机名">
          <el-input v-model="filters.hostname" placeholder="请输入主机名" clearable />
        </el-form-item>
        <el-form-item label="IP">
          <el-input v-model="filters.ip" placeholder="请输入 IP" clearable />
        </el-form-item>
        <el-form-item label="环境">
          <el-select v-model="filters.env" placeholder="请选择" clearable>
            <el-option label="生产" value="production" />
            <el-option label="测试" value="testing" />
            <el-option label="开发" value="development" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="请选择" clearable>
            <el-option label="在线" value="online" />
            <el-option label="离线" value="offline" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadHosts">搜索</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="hosts" v-loading="loading" border stripe height="500" :row-key="(row) => row.id" :max-height="500">
        <el-table-column prop="hostname" label="主机名" min-width="150" />
        <el-table-column prop="ip" label="IP 地址" min-width="130" />
        <el-table-column prop="os_type" label="操作系统" width="100" />
        <el-table-column prop="group_name" label="所属分组" width="120" />
        <el-table-column prop="env" label="环境" width="80">
          <template #default="{ row }">
            <el-tag :type="envTagType(row.env)">{{ envLabel(row.env) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'online' ? 'success' : 'danger'">{{ row.status === 'online' ? '在线' : '离线' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="connector" label="连接方式" width="100" />
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewHost(row)">详情</el-button>
            <el-button size="small" type="primary" @click="checkConn(row)" :loading="row._checking">连通性</el-button>
            <el-button size="small" @click="showEditDialog(row)" v-if="auth.hasPerm('asset:host:update')">编辑</el-button>
            <el-popconfirm title="确定删除该主机吗？" @confirm="handleDelete(row)" v-if="auth.hasPerm('asset:host:delete')">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.size"
        :total="pagination.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadHosts"
        @current-change="loadHosts"
        class="pagination"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑主机' : '新增主机'" width="600px">
      <el-form :model="form" label-width="100px" ref="formRef" :rules="rules">
        <el-form-item label="主机名" prop="hostname">
          <el-input v-model="form.hostname" placeholder="请输入主机名" />
        </el-form-item>
        <el-form-item label="IP 地址" prop="ip">
          <el-input v-model="form.ip" placeholder="请输入 IP 地址" />
        </el-form-item>
        <el-form-item label="操作系统" prop="os_type">
          <el-select v-model="form.os_type" placeholder="请选择">
            <el-option label="Linux" value="linux" />
            <el-option label="Windows" value="windows" />
            <el-option label="macOS" value="macos" />
          </el-select>
        </el-form-item>
        <el-form-item label="系统版本">
          <el-input v-model="form.os_version" placeholder="如 Ubuntu 22.04" />
        </el-form-item>
        <el-form-item label="所属分组" prop="group_id">
          <el-tree-select v-model="form.group_id" :data="groupTree" :props="{ label: 'name', value: 'id' }" placeholder="请选择分组" />
        </el-form-item>
        <el-form-item label="环境" prop="env">
          <el-select v-model="form.env" placeholder="请选择">
            <el-option label="生产" value="production" />
            <el-option label="测试" value="testing" />
            <el-option label="开发" value="development" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签">
          <el-select v-model="form.tags" multiple filterable allow-create placeholder="请输入标签">
            <el-option v-for="tag in form.tags" :key="tag" :label="tag" :value="tag" />
          </el-select>
        </el-form-item>
        <el-form-item label="连接方式">
          <el-select v-model="form.connector" placeholder="请选择">
            <el-option label="Agent" value="agent" />
            <el-option label="SSH" value="ssh" />
          </el-select>
        </el-form-item>
        <el-form-item label="敏感级别">
          <el-select v-model="form.sensitivity_level" placeholder="请选择">
            <el-option label="普通" value="normal" />
            <el-option label="敏感" value="sensitive" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" placeholder="请输入备注" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importVisible" title="导入 CSV" width="500px">
      <el-upload
        ref="uploadRef"
        :auto-upload="false"
        :limit="1"
        accept=".csv"
        :on-change="handleFileChange"
      >
        <template #trigger>
          <el-button type="primary">选择文件</el-button>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="importVisible = false">取消</el-button>
        <el-button type="primary" :loading="importLoading" @click="handleImport">确定导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { getHosts, createHost, updateHost, deleteHost, importHosts, exportHosts, checkConnection, getGroupsTree } from '../../api/assets'
import type { HostOut, GroupOut } from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()
const router = useRouter()

const hosts = ref<(HostOut & { _checking?: boolean })[]>([])
const loading = ref(false)
const pagination = reactive({ page: 1, size: 10, total: 0 })
const filters = reactive({ hostname: '', ip: '', env: '', status: '' })

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(0)
const submitLoading = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({
  hostname: '',
  ip: '',
  os_type: 'linux',
  os_version: '',
  group_id: 0,
  env: 'production',
  tags: [] as string[],
  connector: 'agent',
  sensitivity_level: 'normal',
  remark: ''
})

const rules = {
  hostname: [{ required: true, message: '请输入主机名', trigger: 'blur' }],
  ip: [{ required: true, message: '请输入 IP 地址', trigger: 'blur' }],
  os_type: [{ required: true, message: '请选择操作系统', trigger: 'change' }],
  group_id: [{ required: true, message: '请选择所属分组', trigger: 'change' }],
  env: [{ required: true, message: '请选择环境', trigger: 'change' }]
}

const groupTree = ref<GroupOut[]>([])

const importVisible = ref(false)
const importLoading = ref(false)
const importFile = ref<File | null>(null)

function envTagType(env: string) {
  const map: Record<string, string> = { production: 'danger', testing: 'warning', development: 'info' }
  return map[env] || 'info'
}

function envLabel(env: string) {
  const map: Record<string, string> = { production: '生产', testing: '测试', development: '开发' }
  return map[env] || env
}

async function loadHosts() {
  loading.value = true
  try {
    const result = await getHosts({
      hostname: filters.hostname || undefined,
      ip: filters.ip || undefined,
      env: filters.env || undefined,
      status: filters.status || undefined,
      page: pagination.page,
      size: pagination.size
    })
    hosts.value = result.list
    pagination.total = result.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function loadGroups() {
  try {
    groupTree.value = await getGroupsTree()
  } catch {
    // ignore
  }
}

function resetFilters() {
  filters.hostname = ''
  filters.ip = ''
  filters.env = ''
  filters.status = ''
  loadHosts()
}

function viewHost(row: HostOut) {
  router.push(`/assets/hosts/${row.id}`)
}

function showCreateDialog() {
  isEdit.value = false
  editId.value = 0
  Object.assign(form, { hostname: '', ip: '', os_type: 'linux', os_version: '', group_id: 0, env: 'production', tags: [], connector: 'agent', sensitivity_level: 'normal', remark: '' })
  dialogVisible.value = true
}

function showEditDialog(row: HostOut) {
  isEdit.value = true
  editId.value = row.id
  Object.assign(form, { hostname: row.hostname, ip: row.ip, os_type: row.os_type, os_version: row.os_version, group_id: row.group_id, env: row.env, tags: row.tags || [], connector: row.connector, sensitivity_level: row.sensitivity_level, remark: row.remark })
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    if (isEdit.value) {
      await updateHost(editId.value, { ...form })
      ElMessage.success('编辑成功')
    } else {
      await createHost({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadHosts()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(row: HostOut) {
  try {
    await deleteHost(row.id)
    ElMessage.success('删除成功')
    loadHosts()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function checkConn(row: HostOut & { _checking?: boolean }) {
  row._checking = true
  try {
    const result = await checkConnection(row.id)
    if (result.ok) {
      ElMessage.success(`连通性正常，延迟 ${result.latency_ms}ms`)
    } else {
      ElMessage.error(`连通性检测失败：${result.detail}`)
    }
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    row._checking = false
  }
}

function showImportDialog() {
  importFile.value = null
  importVisible.value = true
}

function handleFileChange(file: File) {
  importFile.value = file
}

async function handleImport() {
  if (!importFile.value) {
    ElMessage.warning('请选择 CSV 文件')
    return
  }
  importLoading.value = true
  try {
    const result = await importHosts(importFile.value)
    ElMessage.success(`导入完成：成功 ${result.success} 条，失败 ${result.failed.length} 条`)
    importVisible.value = false
    loadHosts()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    importLoading.value = false
  }
}

async function handleExport() {
  try {
    const blob = await exportHosts()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `hosts_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => {
  loadHosts()
  loadGroups()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-form {
  margin-bottom: 16px;
}
.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}
</style>