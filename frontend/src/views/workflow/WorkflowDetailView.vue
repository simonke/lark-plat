<template>
  <div class="page" v-loading="loading">
    <el-card>
      <template #header>
        <div class="toolbar">
          <div class="left">
            <el-button @click="goBack">返回</el-button>
            <span class="title">{{ wf?.name || `编排 #${workflowId}` }}</span>
            <el-tag v-if="wf" size="small" type="info">v{{ wf.current_version }}</el-tag>
            <el-tag v-if="wf" size="small" :type="wf.enabled ? 'success' : 'info'">
              {{ wf.enabled ? '启用' : '停用' }}
            </el-tag>
          </div>
          <div v-if="wf">
            <el-button v-perm="'workflow:run'" type="success" @click="onRun">运行</el-button>
            <el-button v-perm="'workflow:version'" @click="openVersion">新建版本</el-button>
            <el-button v-perm="'workflow:edit'" @click="startEdit">编辑</el-button>
            <el-button v-perm="'workflow:del'" type="danger" plain @click="onDelete">删除</el-button>
          </div>
        </div>
      </template>

      <template v-if="wf">
        <el-form v-if="editing" :model="editForm" label-width="90px">
          <el-form-item label="名称"><el-input v-model="editForm.name" maxlength="128" /></el-form-item>
          <el-form-item label="描述">
            <el-input v-model="editForm.description" type="textarea" :rows="2" maxlength="512" />
          </el-form-item>
          <el-form-item label="启用">
            <el-switch v-model="editForm.enabled" :active-value="1" :inactive-value="0" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="saving" @click="onSaveEdit">保存</el-button>
            <el-button @click="editing = false">取消</el-button>
          </el-form-item>
        </el-form>

        <template v-else>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="名称">{{ wf.name }}</el-descriptions-item>
            <el-descriptions-item label="当前版本">v{{ wf.current_version }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ wf.enabled ? '启用' : '停用' }}</el-descriptions-item>
            <el-descriptions-item label="创建人">{{ wf.created_by ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(wf.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ formatTime(wf.updated_at) }}</el-descriptions-item>
            <el-descriptions-item label="描述" :span="2">{{ wf.description || '-' }}</el-descriptions-item>
          </el-descriptions>

          <el-divider content-position="left">当前定义 (v{{ wf.current_version }})</el-divider>
          <el-table :data="currentNodes" border size="small">
            <el-table-column prop="key" label="节点" width="140" />
            <el-table-column label="类型" width="120">
              <template #default="{ row }">{{ nodeTypeLabel(row.type) }}</template>
            </el-table-column>
            <el-table-column label="依赖" min-width="160">
              <template #default="{ row }">{{ (row.depends_on || []).join(', ') || '-' }}</template>
            </el-table-column>
            <el-table-column label="成功后继" min-width="160">
              <template #default="{ row }">{{ (row.on_success || []).join(', ') || '-' }}</template>
            </el-table-column>
            <el-table-column label="失败后继" min-width="160">
              <template #default="{ row }">{{ (row.on_failure || []).join(', ') || '-' }}</template>
            </el-table-column>
          </el-table>
          <div v-if="!currentNodes.length" class="empty">（无节点）</div>
        </template>

        <el-divider content-position="left">版本历史</el-divider>
        <el-table :data="versions" border size="small">
          <el-table-column label="版本" width="80">
            <template #default="{ row }">v{{ row.version }}</template>
          </el-table-column>
          <el-table-column label="编辑人" width="100">
            <template #default="{ row }">{{ row.editor_id ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="时间" width="180">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="200" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="viewVersion(row)">查看</el-button>
              <el-button
                v-if="row.version !== wf.current_version"
                v-perm="'workflow:rollback'"
                size="small"
                type="warning"
                @click="onRollback(row.version)"
              >
                回滚
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <el-dialog v-model="versionVisible" title="新建版本" width="640px">
      <el-form label-width="90px">
        <el-form-item label="定义 (JSON)">
          <el-input v-model="versionDef" type="textarea" :rows="12" spellcheck="false" />
        </el-form-item>
        <el-form-item label="变更说明"><el-input v-model="versionChangeLog" maxlength="256" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="versionVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreateVersion">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="viewVisible" :title="`版本 v${viewRow?.version ?? ''}`" width="640px">
      <pre class="json">{{ viewText }}</pre>
      <template #footer>
        <el-button @click="viewVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getWorkflow,
  updateWorkflow,
  deleteWorkflow,
  listWorkflowVersions,
  createWorkflowVersion,
  rollbackWorkflow,
  runWorkflow,
} from '../../api/workflow'
import { extractError } from '../../api/http'
import type { WorkflowDefinition, WorkflowOut, WorkflowVersion } from '../../api/types'
import { formatDefinition, formatTime, nodeTypeLabel, parseDefinition } from './helpers'

const route = useRoute()
const router = useRouter()
const workflowId = Number(route.params.id)

const loading = ref(false)
const saving = ref(false)
const wf = ref<WorkflowOut | null>(null)
const versions = ref<WorkflowVersion[]>([])
const editing = ref(false)
const editForm = reactive({ name: '', description: '', enabled: 1 })

const currentNodes = computed(() => wf.value?.definition?.nodes ?? [])

const versionVisible = ref(false)
const versionDef = ref(formatDefinition(null))
const versionChangeLog = ref('')
const viewVisible = ref(false)
const viewRow = ref<WorkflowVersion | null>(null)
const viewText = ref('')

async function load() {
  loading.value = true
  try {
    wf.value = await getWorkflow(workflowId)
    editForm.name = wf.value.name
    editForm.description = wf.value.description
    editForm.enabled = wf.value.enabled
    const vres = await listWorkflowVersions(workflowId)
    versions.value = vres.list
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function startEdit() {
  if (!wf.value) return
  editForm.name = wf.value.name
  editForm.description = wf.value.description
  editForm.enabled = wf.value.enabled
  editing.value = true
}

async function onSaveEdit() {
  if (!editForm.name.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    await updateWorkflow(workflowId, {
      name: editForm.name,
      description: editForm.description,
      enabled: editForm.enabled,
    })
    ElMessage.success('已保存')
    editing.value = false
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

function openVersion() {
  versionDef.value = formatDefinition(wf.value?.definition ?? null)
  versionChangeLog.value = ''
  versionVisible.value = true
}

async function onCreateVersion() {
  let definition: WorkflowDefinition
  try {
    definition = parseDefinition(versionDef.value)
  } catch (e) {
    ElMessage.error((e as Error).message)
    return
  }
  saving.value = true
  try {
    await createWorkflowVersion(workflowId, { definition, change_log: versionChangeLog.value })
    ElMessage.success('已生成新版本')
    versionVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onRollback(version: number) {
  try {
    await ElMessageBox.confirm(`确定回滚到 v${version} 吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await rollbackWorkflow(workflowId, version)
    ElMessage.success('已回滚')
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

function viewVersion(row: WorkflowVersion) {
  viewRow.value = row
  viewText.value = formatDefinition(row.definition)
  viewVisible.value = true
}

function newIdempotencyKey(): string {
  try {
    return crypto.randomUUID()
  } catch {
    return `wf-${Date.now()}-${Math.random().toString(16).slice(2)}`
  }
}

async function onRun() {
  try {
    const res = await runWorkflow(workflowId, { trigger_type: 'manual' }, newIdempotencyKey())
    ElMessage.success('已触发运行')
    router.push(`/workflow-runs/${res.run_id}`)
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function onDelete() {
  try {
    await ElMessageBox.confirm(`确定删除编排「${wf.value?.name}」吗？被运行记录引用时将被拒绝。`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteWorkflow(workflowId)
    ElMessage.success('已删除')
    router.push('/workflows')
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

function goBack() {
  router.push('/workflows')
}

onMounted(load)
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
.json {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  margin: 0;
  max-height: 60vh;
  overflow: auto;
}
</style>
