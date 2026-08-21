<template>
  <div class="host-detail-view">
    <el-page-header @back="goBack" title="返回主机列表">
      <template #content>
        <span class="page-header-title">{{ host?.hostname || '加载中...' }}</span>
      </template>
    </el-page-header>

    <el-card v-loading="loading" class="detail-card">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="主机名">{{ host?.hostname }}</el-descriptions-item>
        <el-descriptions-item label="IP 地址">{{ host?.ip }}</el-descriptions-item>
        <el-descriptions-item label="操作系统">{{ host?.os_type }}</el-descriptions-item>
        <el-descriptions-item label="系统版本">{{ host?.os_version }}</el-descriptions-item>
        <el-descriptions-item label="所属分组">{{ host?.group_name }}</el-descriptions-item>
        <el-descriptions-item label="环境">
          <el-tag :type="envTagType(host?.env)">{{ envLabel(host?.env) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="host?.status === 'online' ? 'success' : 'danger'">{{ host?.status === 'online' ? '在线' : '离线' }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="连接方式">{{ host?.connector }}</el-descriptions-item>
        <el-descriptions-item label="敏感级别">{{ host?.sensitivity_level }}</el-descriptions-item>
        <el-descriptions-item label="标签">
          <el-tag v-for="tag in host?.tags" :key="tag" class="tag-item">{{ tag }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ host?.created_at }}</el-descriptions-item>
        <el-descriptions-item label="更新时间">{{ host?.updated_at }}</el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ host?.remark }}</el-descriptions-item>
      </el-descriptions>

      <div class="actions">
        <el-button type="primary" @click="checkConn" :loading="connLoading">连通性检测</el-button>
      </div>
    </el-card>

    <el-card class="credential-card">
      <template #header>
        <div class="card-header">
          <span>凭据管理</span>
          <el-button type="primary" size="small" @click="showCreateCredential" v-if="auth.hasPerm('asset:cred:create')">新增凭据</el-button>
        </div>
      </template>

      <el-table :data="credentials" v-loading="credLoading" border stripe>
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.type === 'password' ? 'info' : 'warning'">{{ row.type === 'password' ? '密码' : '密钥' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="secret_mask" label="密钥/密码" min-width="200" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" @click="showEditCredential(row)" v-if="auth.hasPerm('asset:cred:update')">编辑</el-button>
            <el-popconfirm title="确定删除该凭据吗？" @confirm="handleDeleteCredential(row)" v-if="auth.hasPerm('asset:cred:delete')">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="credDialogVisible" :title="isCredEdit ? '编辑凭据' : '新增凭据'" width="500px">
      <el-form :model="credForm" label-width="80px" ref="credFormRef" :rules="credRules">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="credForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="类型" prop="type">
          <el-select v-model="credForm.type" placeholder="请选择">
            <el-option label="密码" value="password" />
            <el-option label="密钥" value="key" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="credForm.type === 'password'" label="密码" :prop="isCredEdit ? undefined : 'secret'">
          <el-input v-model="credForm.secret" type="password" :placeholder="isCredEdit ? '不填则保留原值' : '请输入密码'" show-password />
        </el-form-item>
        <el-form-item v-if="credForm.type === 'key'" label="私钥" :prop="isCredEdit ? undefined : 'key'">
          <el-input v-model="credForm.key" type="textarea" :rows="4" :placeholder="isCredEdit ? '不填则保留原值' : '请输入私钥内容'" />
        </el-form-item>
        <el-form-item v-if="credForm.type === 'key'" label="密码短语">
          <el-input v-model="credForm.passphrase" type="password" placeholder="请输入密码短语（可选）" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="credDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="credSubmitLoading" @click="handleCredSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { getHost, checkConnection, getCredentials, createCredential, updateCredential, deleteCredential } from '../../api/assets'
import type { HostOut, CredentialOut } from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const hostId = Number(route.params.id)

const host = ref<HostOut | null>(null)
const loading = ref(false)
const connLoading = ref(false)

const credentials = ref<CredentialOut[]>([])
const credLoading = ref(false)
const credDialogVisible = ref(false)
const isCredEdit = ref(false)
const credEditId = ref(0)
const credSubmitLoading = ref(false)
const credFormRef = ref<FormInstance>()
const credForm = reactive({ username: '', type: 'password' as 'password' | 'key', secret: '', key: '', passphrase: '' })

const credRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  secret: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  key: [{ required: true, message: '请输入私钥', trigger: 'blur' }]
}

function envTagType(env?: string) {
  const map: Record<string, string> = { production: 'danger', testing: 'warning', development: 'info' }
  return map[env || ''] || 'info'
}

function envLabel(env?: string) {
  const map: Record<string, string> = { production: '生产', testing: '测试', development: '开发' }
  return map[env || ''] || env || ''
}

function goBack() {
  router.push('/assets/hosts')
}

async function loadHost() {
  loading.value = true
  try {
    host.value = await getHost(hostId)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function loadCredentials() {
  credLoading.value = true
  try {
    const all = await getCredentials()
    credentials.value = all.filter(c => c.host_id === hostId)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    credLoading.value = false
  }
}

async function checkConn() {
  connLoading.value = true
  try {
    const result = await checkConnection(hostId)
    if (result.ok) {
      ElMessage.success(`连通性正常，延迟 ${result.latency_ms}ms`)
    } else {
      ElMessage.error(`连通性检测失败：${result.detail}`)
    }
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    connLoading.value = false
  }
}

function showCreateCredential() {
  isCredEdit.value = false
  credEditId.value = 0
  Object.assign(credForm, { username: '', type: 'password', secret: '', key: '', passphrase: '' })
  credDialogVisible.value = true
}

function showEditCredential(row: CredentialOut) {
  isCredEdit.value = true
  credEditId.value = row.id
  Object.assign(credForm, { username: row.username, type: row.type, secret: '', key: '', passphrase: '' })
  credDialogVisible.value = true
}

async function handleCredSubmit() {
  const valid = await credFormRef.value?.validate().catch(() => false)
  if (!valid) return
  credSubmitLoading.value = true
  try {
    if (isCredEdit.value) {
      const payload: Record<string, unknown> = { username: credForm.username }
      if (credForm.type === 'password' && credForm.secret) payload.secret = credForm.secret
      if (credForm.type === 'key' && credForm.key) payload.key = credForm.key
      if (credForm.passphrase) payload.passphrase = credForm.passphrase
      await updateCredential(credEditId.value, payload)
      ElMessage.success('编辑成功')
    } else {
      await createCredential({ host_id: hostId, ...credForm })
      ElMessage.success('创建成功')
    }
    credDialogVisible.value = false
    loadCredentials()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    credSubmitLoading.value = false
  }
}

async function handleDeleteCredential(row: CredentialOut) {
  try {
    await deleteCredential(row.id)
    ElMessage.success('删除成功')
    loadCredentials()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => {
  loadHost()
  loadCredentials()
})
</script>

<style scoped>
.detail-card {
  margin-top: 16px;
}
.credential-card {
  margin-top: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.actions {
  margin-top: 16px;
}
.tag-item {
  margin-right: 8px;
}
.page-header-title {
  font-size: 18px;
  font-weight: 600;
}
</style>