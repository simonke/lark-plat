<template>
  <div class="credentials-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>凭据管理</span>
          <el-button type="primary" @click="showCreateDialog" v-if="auth.hasPerm('asset:cred:create')">新增凭据</el-button>
        </div>
      </template>

      <el-table :data="credentials" v-loading="loading" border stripe>
        <el-table-column prop="host_hostname" label="主机" min-width="150" />
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
            <el-button size="small" @click="showEditDialog(row)" v-if="auth.hasPerm('asset:cred:update')">编辑</el-button>
            <el-popconfirm title="确定删除该凭据吗？" @confirm="handleDelete(row)" v-if="auth.hasPerm('asset:cred:delete')">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑凭据' : '新增凭据'" width="500px">
      <el-form :model="form" label-width="80px" ref="formRef" :rules="rules">
        <el-form-item label="主机" prop="host_id" v-if="!isEdit">
          <el-select v-model="form.host_id" placeholder="请选择主机" filterable>
            <el-option v-for="h in hostList" :key="h.id" :label="`${h.hostname} (${h.ip})`" :value="h.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="类型" prop="type">
          <el-select v-model="form.type" placeholder="请选择">
            <el-option label="密码" value="password" />
            <el-option label="密钥" value="key" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.type === 'password'" label="密码" :prop="isEdit ? undefined : 'secret'">
          <el-input v-model="form.secret" type="password" :placeholder="isEdit ? '不填则保留原值' : '请输入密码'" show-password />
        </el-form-item>
        <el-form-item v-if="form.type === 'key'" label="私钥" :prop="isEdit ? undefined : 'key'">
          <el-input v-model="form.key" type="textarea" :rows="4" :placeholder="isEdit ? '不填则保留原值' : '请输入私钥内容'" />
        </el-form-item>
        <el-form-item v-if="form.type === 'key'" label="密码短语">
          <el-input v-model="form.passphrase" type="password" placeholder="请输入密码短语（可选）" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitLoading" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import { getCredentials, createCredential, updateCredential, deleteCredential, getHosts } from '../../api/assets'
import type { CredentialOut, HostOut } from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()

const credentials = ref<CredentialOut[]>([])
const hostList = ref<HostOut[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(0)
const submitLoading = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ host_id: 0, username: '', type: 'password', secret: '', key: '', passphrase: '' })

const rules = {
  host_id: [{ required: true, message: '请选择主机', trigger: 'change' }],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  type: [{ required: true, message: '请选择类型', trigger: 'change' }],
  secret: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  key: [{ required: true, message: '请输入私钥', trigger: 'blur' }]
}

async function loadCredentials() {
  loading.value = true
  try {
    credentials.value = await getCredentials()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function loadHosts() {
  try {
    const result = await getHosts({ size: 1000 })
    hostList.value = result.list
  } catch {
    // ignore
  }
}

function showCreateDialog() {
  isEdit.value = false
  editId.value = 0
  Object.assign(form, { host_id: 0, username: '', type: 'password', secret: '', key: '', passphrase: '' })
  dialogVisible.value = true
}

function showEditDialog(row: CredentialOut) {
  isEdit.value = true
  editId.value = row.id
  Object.assign(form, { host_id: row.host_id, username: row.username, type: row.type, secret: '', key: '', passphrase: '' })
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    if (isEdit.value) {
      const payload: Record<string, unknown> = { username: form.username }
      if (form.type === 'password' && form.secret) payload.secret = form.secret
      if (form.type === 'key' && form.key) payload.key = form.key
      if (form.passphrase) payload.passphrase = form.passphrase
      await updateCredential(editId.value, payload)
      ElMessage.success('编辑成功')
    } else {
      await createCredential({ host_id: form.host_id, username: form.username, type: form.type as 'password' | 'key', secret: form.secret, key: form.key, passphrase: form.passphrase })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadCredentials()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(row: CredentialOut) {
  try {
    await deleteCredential(row.id)
    ElMessage.success('删除成功')
    loadCredentials()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => {
  loadCredentials()
  loadHosts()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>