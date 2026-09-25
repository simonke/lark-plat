<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">CI/CD 凭据</span>
          <el-button type="primary" v-perm="'cicd:provider:add'" @click="openCreate">新建凭据</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load(1)">
        <el-form-item label="名称">
          <el-input v-model="query.name" placeholder="按名称过滤" clearable style="width: 180px" @keyup.enter="load(1)" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="query.type" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="o in PROVIDER_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="类型" width="140">
          <template #default="{ row }">{{ providerTypeLabel(row.type) }}</template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="endpoint" label="地址" min-width="220" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="连通性" width="110">
          <template #default="{ row }">
            <el-tag :type="providerStatusTag(row.status)" size="small" effect="plain">
              {{ row.status || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近心跳" width="180">
          <template #default="{ row }">{{ formatTime(row.last_heartbeat) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'cicd:provider:test'" :loading="testingId === row.id" @click="onTest(row)">
              测试
            </el-button>
            <el-button size="small" v-perm="'cicd:provider:edit'" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain v-perm="'cicd:provider:del'" @click="onDelete(row)">删除</el-button>
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

    <el-dialog v-model="formVisible" :title="editingId ? '编辑凭据' : '新建凭据'" width="560px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="类型">
          <el-select v-model="form.type" :disabled="!!editingId" style="width: 100%">
            <el-option v-for="o in PROVIDER_TYPE_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="128" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.endpoint" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="密钥">
          <el-input
            v-model="form.secret"
            type="password"
            show-password
            :placeholder="editingId ? '留空则不修改' : '访问令牌 / 密码'"
          />
          <div class="hint">逐值密文存储；后端不回显明文，留空表示不变更。</div>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.enabled" :active-value="1" :inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listCicdProviders,
  createCicdProvider,
  updateCicdProvider,
  deleteCicdProvider,
  testCicdProvider,
} from '../../api/cicd'
import { extractError } from '../../api/http'
import type { CicdProviderOut, CicdProviderQuery, CicdProviderType } from '../../api/types'
import { PROVIDER_TYPE_OPTIONS, formatTime, providerStatusTag, providerTypeLabel } from './helpers'

const loading = ref(false)
const saving = ref(false)
const testingId = ref<number | null>(null)
const rows = ref<CicdProviderOut[]>([])
const total = ref(0)
const query = reactive<CicdProviderQuery>({ page: 1, size: 10 })

const formVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive<{
  type: CicdProviderType
  name: string
  endpoint: string
  secret: string
  enabled: number
}>({ type: 'gitlab', name: '', endpoint: '', secret: '', enabled: 1 })

async function load(page?: number) {
  if (page) query.page = page
  loading.value = true
  try {
    const res = await listCicdProviders({
      name: query.name || undefined,
      type: query.type || undefined,
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
  query.type = undefined
  query.page = 1
  load()
}

function openCreate() {
  editingId.value = null
  form.type = 'gitlab'
  form.name = ''
  form.endpoint = ''
  form.secret = ''
  form.enabled = 1
  formVisible.value = true
}

function openEdit(row: CicdProviderOut) {
  editingId.value = row.id
  form.type = row.type
  form.name = row.name
  form.endpoint = row.endpoint
  form.secret = ''
  form.enabled = row.enabled
  formVisible.value = true
}

async function onSubmit() {
  if (!form.name.trim() || !form.endpoint.trim()) {
    ElMessage.warning('请填写名称与地址')
    return
  }
  saving.value = true
  try {
    const config = form.secret ? { token: form.secret } : undefined
    if (editingId.value) {
      await updateCicdProvider(editingId.value, {
        name: form.name,
        endpoint: form.endpoint,
        enabled: form.enabled,
        config,
      })
    } else {
      await createCicdProvider({
        type: form.type,
        name: form.name,
        endpoint: form.endpoint,
        enabled: form.enabled,
        config,
      })
    }
    ElMessage.success('已保存')
    formVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onDelete(row: CicdProviderOut) {
  try {
    await ElMessageBox.confirm(`确定删除凭据「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteCicdProvider(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function onTest(row: CicdProviderOut) {
  testingId.value = row.id
  try {
    const res = await testCicdProvider(row.id)
    if (res.ok) {
      ElMessage.success(`连通正常${res.latency_ms != null ? `（${res.latency_ms}ms）` : ''}`)
    } else {
      ElMessage.error(res.error_message || '连通失败')
    }
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    testingId.value = null
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
