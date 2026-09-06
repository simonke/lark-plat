<template>
  <div class="scripts-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>脚本管理</span>
          <el-button type="primary" @click="showCreateDialog" v-if="auth.hasPerm('script:add')">新增脚本</el-button>
        </div>
      </template>

      <el-form :inline="true" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="query.name" placeholder="按名称过滤" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="类型">
          <el-input v-model="query.type" placeholder="shell/python/bat" clearable @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleSearch" v-if="auth.hasPerm('script:list')">查询</el-button>
          <el-button @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="160" show-overflow-tooltip />
        <el-table-column prop="type" label="类型" width="100" />
        <el-table-column prop="current_version" label="当前版本" width="90" />
        <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button size="small" @click="showVersionsDialog(row)" v-if="auth.hasPerm('script:version')">版本</el-button>
            <el-button size="small" type="success" @click="showTestDialog(row)" v-if="auth.hasPerm('script:test')">试运行</el-button>
            <el-button size="small" @click="showEditDialog(row)" v-if="auth.hasPerm('script:edit')">编辑</el-button>
            <el-popconfirm title="确定删除该脚本吗？" @confirm="handleDelete(row)" v-if="auth.hasPerm('script:del')">
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

    <el-dialog v-model="createVisible" title="新增脚本" width="640px">
      <el-form :model="createForm" label-width="90px" ref="createFormRef" :rules="createRules">
        <el-form-item label="名称" prop="name">
          <el-input v-model="createForm.name" placeholder="请输入脚本名称" />
        </el-form-item>
        <el-form-item label="类型" prop="type">
          <el-select v-model="createForm.type" placeholder="请选择类型" style="width: 200px">
            <el-option label="shell" value="shell" />
            <el-option label="python" value="python" />
            <el-option label="bat" value="bat" />
            <el-option label="powershell" value="powershell" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input v-model="createForm.content" type="textarea" :rows="10" placeholder="脚本内容" />
        </el-form-item>
        <el-form-item label="参数定义">
          <el-input v-model="createForm.paramsDefText" type="textarea" :rows="3" placeholder='JSON，如 {"target": {"type": "string", "required": true}}' />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="createForm.remark" type="textarea" :rows="2" placeholder="备注（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleCreate">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑脚本（保存为新版本）" width="640px">
      <el-descriptions :column="2" border size="small" class="edit-meta">
        <el-descriptions-item label="ID">{{ editRow?.id }}</el-descriptions-item>
        <el-descriptions-item label="名称">{{ editRow?.name }}</el-descriptions-item>
      </el-descriptions>
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="内容">
          <el-input v-model="editForm.content" type="textarea" :rows="10" placeholder="留空则沿用当前版本内容" />
        </el-form-item>
        <el-form-item label="参数定义">
          <el-input v-model="editForm.paramsDefText" type="textarea" :rows="3" placeholder="JSON（可选）" />
        </el-form-item>
        <el-form-item label="变更说明">
          <el-input v-model="editForm.change_log" type="textarea" :rows="2" placeholder="本次变更说明" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="editForm.remark" type="textarea" :rows="2" placeholder="备注（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleEdit">保存新版本</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="versionsVisible" :title="`版本历史 - ${versionsRow?.name ?? ''}`" width="760px">
      <el-table :data="versions" v-loading="versionsLoading" border size="small">
        <el-table-column prop="version" label="版本" width="70" />
        <el-table-column prop="change_log" label="变更说明" min-width="180" show-overflow-tooltip />
        <el-table-column prop="created_by" label="创建人ID" width="90" />
        <el-table-column prop="created_at" label="创建时间" min-width="165" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" @click="showVersionContent(row)">查看</el-button>
            <el-popconfirm
              title="确定回滚到该版本吗？"
              @confirm="handleRollback(row)"
              v-if="auth.hasPerm('script:rollback')"
            >
              <template #reference>
                <el-button size="small" type="warning">回滚</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog v-model="versionContentVisible" :title="`版本 ${versionContentRow?.version ?? ''} 内容`" width="640px">
      <el-input :model-value="versionContentRow?.content ?? ''" type="textarea" :rows="16" readonly />
    </el-dialog>

    <el-dialog v-model="testVisible" :title="`试运行 - ${testRow?.name ?? ''}`" width="560px">
      <el-form label-width="90px">
        <el-form-item label="参数 JSON">
          <el-input v-model="testParamsText" type="textarea" :rows="4" placeholder='{"key": "value"}（可选）' />
        </el-form-item>
      </el-form>
      <el-alert v-if="testResult" :title="testResult.ok ? '校验通过' : '校验未通过'" :type="testResult.ok ? 'success' : 'error'" :closable="false">
        <div v-if="!testResult.ok">
          <div v-for="(err, i) in testResult.errors" :key="i">{{ err }}</div>
        </div>
      </el-alert>
      <template #footer>
        <el-button @click="testVisible = false">关闭</el-button>
        <el-button type="primary" :loading="testLoading" @click="handleTest">执行校验</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { getScripts, getScript, createScript, updateScript, deleteScript, getVersions, rollbackScript, testScript } from '../../api/scripts'
import type { ScriptOut } from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()

const rows = ref<ScriptOut[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ name: '', type: '', page: 1, size: 10 })

function parseJsonOrNull(text: string): Record<string, unknown> | null | undefined {
  const trimmed = text.trim()
  if (!trimmed) return null
  return JSON.parse(trimmed) as Record<string, unknown>
}

async function loadRows() {
  loading.value = true
  try {
    const page = await getScripts({
      name: query.name || undefined,
      type: query.type || undefined,
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
  query.type = ''
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

const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const submitLoading = ref(false)
const createForm = reactive({ name: '', type: 'shell', content: '', paramsDefText: '', remark: '' })
const createRules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入脚本内容', trigger: 'blur' }],
}

function showCreateDialog() {
  Object.assign(createForm, { name: '', type: 'shell', content: '', paramsDefText: '', remark: '' })
  createVisible.value = true
}

async function handleCreate() {
  const valid = await createFormRef.value?.validate().catch(() => false)
  if (!valid) return
  let params_def: Record<string, unknown> | null
  try {
    params_def = parseJsonOrNull(createForm.paramsDefText) ?? null
  } catch {
    ElMessage.error('参数定义不是合法 JSON')
    return
  }
  submitLoading.value = true
  try {
    await createScript({
      name: createForm.name,
      type: createForm.type,
      content: createForm.content,
      params_def,
      remark: createForm.remark || undefined,
    })
    ElMessage.success('创建成功')
    createVisible.value = false
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

const editVisible = ref(false)
const editRow = ref<ScriptOut | null>(null)
const editForm = reactive({ content: '', paramsDefText: '', change_log: '', remark: '' })

async function showEditDialog(row: ScriptOut) {
  editRow.value = row
  Object.assign(editForm, { content: '', paramsDefText: '', change_log: '', remark: row.remark })
  try {
    const detail = await getScript(row.id)
    editForm.content = detail.content
    editForm.paramsDefText = detail.params_def ? JSON.stringify(detail.params_def, null, 2) : ''
  } catch (e) {
    ElMessage.error(extractError(e))
    return
  }
  editVisible.value = true
}

async function handleEdit() {
  if (!editRow.value) return
  let params_def: Record<string, unknown> | null | undefined
  try {
    params_def = parseJsonOrNull(editForm.paramsDefText)
  } catch {
    ElMessage.error('参数定义不是合法 JSON')
    return
  }
  submitLoading.value = true
  try {
    await updateScript(editRow.value.id, {
      content: editForm.content || undefined,
      params_def,
      change_log: editForm.change_log || undefined,
      remark: editForm.remark || undefined,
    })
    ElMessage.success('已保存为新版本')
    editVisible.value = false
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(row: ScriptOut) {
  try {
    await deleteScript(row.id)
    ElMessage.success('删除成功')
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const versionsVisible = ref(false)
const versionsLoading = ref(false)
const versionsRow = ref<ScriptOut | null>(null)
const versions = ref<{ id: number; version: number; content: string; change_log: string; created_by: number | null; created_at: string }[]>([])
const versionContentVisible = ref(false)
const versionContentRow = ref<{ version: number; content: string } | null>(null)

async function showVersionsDialog(row: ScriptOut) {
  versionsRow.value = row
  versionsVisible.value = true
  versionsLoading.value = true
  try {
    versions.value = await getVersions(row.id)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    versionsLoading.value = false
  }
}

function showVersionContent(row: { version: number; content: string }) {
  versionContentRow.value = row
  versionContentVisible.value = true
}

async function handleRollback(row: { version: number }) {
  if (!versionsRow.value) return
  try {
    await rollbackScript(versionsRow.value.id, { version: row.version })
    ElMessage.success(`已回滚到版本 ${row.version}`)
    versionsVisible.value = false
    loadRows()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const testVisible = ref(false)
const testLoading = ref(false)
const testRow = ref<ScriptOut | null>(null)
const testParamsText = ref('')
const testResult = ref<{ ok: boolean; errors: string[] } | null>(null)

function showTestDialog(row: ScriptOut) {
  testRow.value = row
  testParamsText.value = ''
  testResult.value = null
  testVisible.value = true
}

async function handleTest() {
  if (!testRow.value) return
  let params: Record<string, unknown> | null
  try {
    params = parseJsonOrNull(testParamsText.value) ?? null
  } catch {
    ElMessage.error('参数不是合法 JSON')
    return
  }
  testLoading.value = true
  try {
    testResult.value = await testScript(testRow.value.id, { params })
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    testLoading.value = false
  }
}

onMounted(() => {
  loadRows()
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
.edit-meta {
  margin-bottom: 12px;
}
</style>
