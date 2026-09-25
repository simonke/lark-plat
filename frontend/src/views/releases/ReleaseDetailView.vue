<template>
  <div class="page" v-loading="loading">
    <el-card>
      <template #header>
        <div class="toolbar">
          <div class="left">
            <el-button @click="goBack">返回</el-button>
            <span class="title">发布 #{{ releaseId }}</span>
            <el-tag v-if="row" :type="releaseStatusTag(row.status)" size="small">
              {{ releaseStatusLabel(row.status) }}
            </el-tag>
          </div>
          <div>
            <el-button :loading="loading" @click="load">刷新</el-button>
            <el-button v-if="row && canCanary(row.status)" v-perm="'release:canary'" type="primary" @click="onAction('canary')">
              灰度
            </el-button>
            <el-button v-if="row && canPromote(row.status)" v-perm="'release:promote'" type="success" @click="onAction('promote')">
              全量
            </el-button>
            <el-button v-if="row && canRollback(row.status)" v-perm="'release:rollback'" type="warning" @click="onAction('rollback')">
              回滚
            </el-button>
            <el-button v-if="row && canCancel(row.status)" v-perm="'release:cancel'" type="danger" @click="onAction('cancel')">
              取消
            </el-button>
          </div>
        </div>
      </template>

      <template v-if="row">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="发布 ID">{{ row.id }}</el-descriptions-item>
          <el-descriptions-item label="应用">{{ row.app }}</el-descriptions-item>
          <el-descriptions-item label="版本">{{ row.version }}</el-descriptions-item>
          <el-descriptions-item label="环境">{{ envLabel(row.env) }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ releaseStatusLabel(row.status) }}</el-descriptions-item>
          <el-descriptions-item label="CI/CD 凭据">{{ row.provider_id }}</el-descriptions-item>
          <el-descriptions-item label="编排运行">{{ row.workflow_run_id ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="回滚自">{{ row.rolled_back_from ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建人">{{ row.created_by ?? '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(row.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ formatTime(row.updated_at) }}</el-descriptions-item>
          <el-descriptions-item label="目标主机">{{ (row.target_host_ids || []).join(', ') || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="row.workflow_run_id" class="linkrow">
          <el-button link type="primary" @click="goRun(row.workflow_run_id)">
            查看编排运行 #{{ row.workflow_run_id }}
          </el-button>
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getRelease,
  canaryRelease,
  promoteRelease,
  rollbackRelease,
  cancelRelease,
} from '../../api/release'
import { extractError } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import type { Release } from '../../api/types'
import { canCanary, canCancel, canPromote, canRollback, envLabel, formatTime, releaseStatusLabel, releaseStatusTag } from './helpers'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const releaseId = Number(route.params.id)

const loading = ref(false)
const row = ref<Release | null>(null)

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

async function load() {
  loading.value = true
  try {
    row.value = await getRelease(releaseId)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function onAction(action: keyof typeof ACTIONS) {
  try {
    await ElMessageBox.confirm(`确定${ACTION_LABEL[action]}该发布吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await ACTIONS[action](releaseId)
    ElMessage.success('已提交')
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

function goBack() {
  router.push('/releases')
}

function goRun(runId: number) {
  router.push(`/workflow-runs/${runId}`)
}

onMounted(() => {
  if (!auth.hasPerm('release:view')) {
    ElMessage.warning('缺少 release:view 权限')
    goBack()
    return
  }
  load()
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
.linkrow {
  margin-top: 12px;
}
</style>
