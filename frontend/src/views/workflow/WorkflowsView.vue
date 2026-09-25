<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">编排 Playbook</span>
          <el-button type="primary" v-perm="'workflow:add'" @click="openCreate">新建编排</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load(1)">
        <el-form-item label="名称">
          <el-input v-model="query.name" placeholder="按名称过滤" clearable style="width: 180px" @keyup.enter="load(1)" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.enabled" clearable placeholder="全部" style="width: 120px">
            <el-option label="启用" :value="1" />
            <el-option label="停用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border @row-click="openDetail">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
        <el-table-column label="当前版本" width="100">
          <template #default="{ row }">v{{ row.current_version }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click.stop="openDetail(row)">详情</el-button>
            <el-button size="small" type="danger" plain v-perm="'workflow:del'" @click.stop="onDelete(row)">删除</el-button>
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
        @change="load()"
      />
    </el-card>

    <el-dialog v-model="createVisible" title="新建编排" width="640px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="128" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" maxlength="512" />
        </el-form-item>
        <el-form-item label="定义 (JSON)">
          <el-input v-model="form.definition" type="textarea" :rows="12" spellcheck="false" />
          <div class="hint">
            形如 {"nodes":[{"key":"a","type":"sleep","config":{},"depends_on":[]}]}；环或超限（nodes≤100、edges≤500）→ 422。
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreate">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listWorkflows, createWorkflow, deleteWorkflow } from '../../api/workflow'
import { extractError } from '../../api/http'
import type { Workflow, WorkflowDefinition, WorkflowQuery } from '../../api/types'
import { formatDefinition, formatTime, parseDefinition } from './helpers'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const rows = ref<Workflow[]>([])
const total = ref(0)
const query = reactive<WorkflowQuery>({ page: 1, size: 10 })

const createVisible = ref(false)
const form = reactive({ name: '', description: '', definition: formatDefinition(null) })

async function load(page?: number) {
  if (page) query.page = page
  loading.value = true
  try {
    const res = await listWorkflows({
      name: query.name || undefined,
      enabled: typeof query.enabled === 'number' ? query.enabled : undefined,
      page: query.page,
      size: query.size,
    })
    rows.value = res.list
    total.value = res.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function reset() {
  query.name = undefined
  query.enabled = undefined
  query.page = 1
  load()
}

function openDetail(row: Workflow) {
  router.push(`/workflows/${row.id}`)
}

function openCreate() {
  form.name = ''
  form.description = ''
  form.definition = formatDefinition(null)
  createVisible.value = true
}

async function onCreate() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  let definition: WorkflowDefinition
  try {
    definition = parseDefinition(form.definition)
  } catch (e) {
    ElMessage.error((e as Error).message)
    return
  }
  saving.value = true
  try {
    await createWorkflow({ name: form.name, description: form.description, definition })
    ElMessage.success('已创建')
    createVisible.value = false
    await load(1)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onDelete(row: Workflow) {
  try {
    await ElMessageBox.confirm(`确定删除编排「${row.name}」吗？被运行记录引用时将被拒绝。`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteWorkflow(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => load(1))
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
.hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
</style>
