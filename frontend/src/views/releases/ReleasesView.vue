<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">发布管理</span>
          <el-button type="primary" v-perm="'release:add'" @click="openCreate">新建发布</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load(1)">
        <el-form-item label="应用">
          <el-input v-model="query.app" placeholder="按应用过滤" clearable style="width: 180px" @keyup.enter="load(1)" />
        </el-form-item>
        <el-form-item label="环境">
          <el-select v-model="query.env" clearable placeholder="全部" style="width: 120px">
            <el-option v-for="o in ENV_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 130px">
            <el-option v-for="o in RELEASE_STATUS_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border @row-click="openDetail">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="app" label="应用" min-width="150" show-overflow-tooltip />
        <el-table-column prop="version" label="版本" width="130" show-overflow-tooltip />
        <el-table-column label="环境" width="90">
          <template #default="{ row }">{{ envLabel(row.env) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="releaseStatusTag(row.status)" size="small">{{ releaseStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="编排运行" width="100">
          <template #default="{ row }">{{ row.workflow_run_id ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'release:view'" @click.stop="openDetail(row)">详情</el-button>
            <el-button v-if="canCanary(row.status)" size="small" v-perm="'release:canary'" @click.stop="onAction(row, 'canary')">
              灰度
            </el-button>
            <el-button v-if="canPromote(row.status)" size="small" type="success" v-perm="'release:promote'" @click.stop="onAction(row, 'promote')">
              全量
            </el-button>
            <el-button v-if="canRollback(row.status)" size="small" type="warning" v-perm="'release:rollback'" @click.stop="onAction(row, 'rollback')">
              回滚
            </el-button>
            <el-button v-if="canCancel(row.status)" size="small" type="danger" plain v-perm="'release:cancel'" @click.stop="onAction(row, 'cancel')">
              取消
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
        @change="load()"
      />
    </el-card>

    <el-dialog v-model="createVisible" title="新建发布" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="CI/CD 凭据">
          <el-select v-model="form.provider_id" placeholder="选择凭据" style="width: 100%">
            <el-option
              v-for="p in providers"
              :key="p.id"
              :label="`${providerTypeLabel(p.type)} · ${p.name}`"
              :value="p.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="应用">
          <el-input v-model="form.app" maxlength="128" />
        </el-form-item>
        <el-form-item label="版本">
          <el-input v-model="form.version" placeholder="1.0.0" maxlength="64" />
        </el-form-item>
        <el-form-item label="环境">
          <el-select v-model="form.env" style="width: 100%">
            <el-option v-for="o in ENV_OPTIONS" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
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
import {
  listReleases,
  createRelease,
  canaryRelease,
  promoteRelease,
  rollbackRelease,
  cancelRelease,
} from '../../api/release'
import { listCicdProviders } from '../../api/cicd'
import { extractError } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import type { CicdProviderOut, Release, ReleaseEnv, ReleaseQuery } from '../../api/types'
import { ENV_OPTIONS, RELEASE_STATUS_OPTIONS, canCanary, canCancel, canPromote, canRollback, envLabel, formatTime, releaseStatusLabel, releaseStatusTag } from './helpers'
import { providerTypeLabel } from '../cicd/helpers'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const saving = ref(false)
const rows = ref<Release[]>([])
const total = ref(0)
const query = reactive<ReleaseQuery>({ page: 1, size: 10 })

const createVisible = ref(false)
const providers = ref<CicdProviderOut[]>([])
const form = reactive<{ provider_id: number; app: string; version: string; env: ReleaseEnv }>({
  provider_id: 0,
  app: '',
  version: '',
  env: 'dev',
})

const ACTIONS = {
  canary: canaryRelease,
  promote: promoteRelease,
  rollback: rollbackRelease,
  cancel: cancelRelease,
}
const ACTION_LABEL: Record<keyof typeof ACTIONS, string> = {
  canary: '灰度',
  promote: '全量',
  rollback: '回滚',
  cancel: '取消',
}

async function load(page?: number) {
  if (page) query.page = page
  loading.value = true
  try {
    const res = await listReleases({
      app: query.app || undefined,
      env: query.env || undefined,
      status: query.status || undefined,
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
  query.app = undefined
  query.env = undefined
  query.status = undefined
  query.page = 1
  load()
}

function openDetail(row: Release) {
  if (!auth.hasPerm('release:view')) {
    ElMessage.warning('缺少 release:view 权限')
    return
  }
  router.push(`/releases/${row.id}`)
}

async function openCreate() {
  try {
    providers.value = (await listCicdProviders({ page: 1, size: 100 })).list
  } catch (e) {
    ElMessage.error(extractError(e))
    return
  }
  form.provider_id = providers.value[0]?.id ?? 0
  form.app = ''
  form.version = ''
  form.env = 'dev'
  createVisible.value = true
}

async function onCreate() {
  if (!form.provider_id) {
    ElMessage.warning('请选择 CI/CD 凭据')
    return
  }
  if (!form.app.trim() || !form.version.trim()) {
    ElMessage.warning('请填写应用与版本')
    return
  }
  saving.value = true
  try {
    await createRelease({
      provider_id: form.provider_id,
      app: form.app,
      version: form.version,
      env: form.env,
    })
    ElMessage.success('已创建')
    createVisible.value = false
    await load(1)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onAction(row: Release, action: keyof typeof ACTIONS) {
  try {
    await ElMessageBox.confirm(`确定${ACTION_LABEL[action]}发布 #${row.id}（${row.app}）吗？`, '提示', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await ACTIONS[action](row.id)
    ElMessage.success('已提交')
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
</style>
