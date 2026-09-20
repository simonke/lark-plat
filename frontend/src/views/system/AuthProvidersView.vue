<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">身份源</span>
          <el-button type="primary" v-perm="'system:auth:provider'" @click="openCreate">新增身份源</el-button>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="code" label="编码" min-width="120" />
        <el-table-column prop="name" label="名称" min-width="140" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled === 1 ? 'success' : 'danger'">
              {{ row.enabled === 1 ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="配置(脱敏)" min-width="200">
          <template #default="{ row }">
            <span class="mask">{{ maskText(row.config_mask) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'system:auth:provider'" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" v-perm="'system:auth:provider'" :loading="testingId === row.id" @click="onTest(row)">
              试测
            </el-button>
            <el-button size="small" v-perm="'system:auth:provider'" @click="onToggle(row)">
              {{ row.enabled === 1 ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" v-perm="'system:auth:provider'" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editorVisible" :title="editingId ? '编辑身份源' : '新增身份源'" width="560px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="名称">
          <el-input v-model="form.name" :maxlength="64" />
        </el-form-item>
        <el-form-item label="编码" v-if="!editingId">
          <el-input v-model="form.code" :maxlength="64" placeholder="留空则由名称生成" />
        </el-form-item>
        <el-form-item label="类型" v-if="!editingId">
          <el-select v-model="form.type" style="width: 100%">
            <el-option label="LDAP" value="ldap" />
            <el-option label="OAuth2" value="oauth2" />
          </el-select>
        </el-form-item>
        <el-form-item label="配置(JSON)">
          <el-input
            v-model="configText"
            type="textarea"
            :rows="8"
            :placeholder="configPlaceholder"
          />
          <div class="hint">{{ configHint }}</div>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.enabled">
            <el-radio :value="1">启用</el-radio>
            <el-radio :value="0">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createAuthProvider,
  deleteAuthProvider,
  listAuthProviders,
  setAuthProviderStatus,
  testAuthProvider,
  updateAuthProvider,
} from '../../api/authProviders'
import type { AuthProviderOut, AuthProviderType } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const saving = ref(false)
const testingId = ref<number | null>(null)
const rows = ref<AuthProviderOut[]>([])

const editorVisible = ref(false)
const editingId = ref<number | null>(null)
const configText = ref('')
const form = reactive({
  name: '',
  code: '',
  type: 'ldap' as AuthProviderType,
  enabled: 1,
})

const configPlaceholders: Record<AuthProviderType, string> = {
  ldap: '{\n  "server_uri": "ldaps://ldap.example.com:636",\n  "bind_dn_template": "uid={username},ou=people,dc=example,dc=com",\n  "base_dn": "ou=people,dc=example,dc=com",\n  "map_key": "email",\n  "password": "",\n  "auto_provision": true,\n  "default_role_codes": ["ops"]\n}',
  oauth2: '{\n  "authorization_endpoint": "https://idp.example.com/oauth/authorize",\n  "token_endpoint": "https://idp.example.com/oauth/token",\n  "client_id": "",\n  "client_secret": "",\n  "redirect_uri": "",\n  "scope": "openid profile email",\n  "map_key": "email",\n  "auto_provision": true,\n  "default_role_codes": ["ops"]\n}',
}

const configPlaceholder = computed(() => configPlaceholders[form.type])
const configHint = computed(() =>
  editingId.value
    ? '密文留空＝保留原配置；如需变更，填写完整 JSON。'
    : '填写该身份源的完整 JSON 配置，密钥字段将以密文存储。',
)

watch(
  () => form.type,
  (t) => {
    if (!editingId.value && !configText.value) {
      configText.value = configPlaceholders[t]
    }
  },
)

async function load() {
  loading.value = true
  try {
    rows.value = await listAuthProviders()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function maskText(mask: Record<string, unknown> | undefined): string {
  if (!mask || Object.keys(mask).length === 0) return '-'
  return Object.keys(mask).join(', ')
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { name: '', code: '', type: 'ldap', enabled: 1 })
  configText.value = configPlaceholders.ldap
  editorVisible.value = true
}

function openEdit(row: AuthProviderOut) {
  editingId.value = row.id
  Object.assign(form, { name: row.name, code: row.code, type: row.type, enabled: row.enabled })
  configText.value = ''
  editorVisible.value = true
}

function parseConfig(): Record<string, unknown> | undefined {
  const text = configText.value.trim()
  if (!text) return undefined
  const parsed = JSON.parse(text)
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('配置须为 JSON 对象')
  }
  return parsed as Record<string, unknown>
}

async function onSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  let config: Record<string, unknown> | undefined
  try {
    config = parseConfig()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '配置 JSON 解析失败')
    return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await updateAuthProvider(editingId.value, {
        name: form.name,
        enabled: form.enabled,
        ...(config ? { config } : {}),
      })
    } else {
      if (!config) {
        ElMessage.warning('请填写配置 JSON')
        return
      }
      await createAuthProvider({
        name: form.name,
        type: form.type,
        ...(form.code ? { code: form.code } : {}),
        config,
        enabled: form.enabled,
      })
    }
    ElMessage.success('保存成功')
    editorVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onTest(row: AuthProviderOut) {
  testingId.value = row.id
  try {
    const result = await testAuthProvider(row.id)
    if (result.ok) {
      ElMessage.success(`试测通过${result.latency_ms != null ? `（${result.latency_ms}ms）` : ''}`)
    } else {
      ElMessage.error(result.error_message || '试测失败')
    }
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    testingId.value = null
  }
}

async function onToggle(row: AuthProviderOut) {
  try {
    await setAuthProviderStatus(row.id, { enabled: row.enabled === 1 ? 0 : 1 })
    ElMessage.success('状态已更新')
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function onDelete(row: AuthProviderOut) {
  try {
    await ElMessageBox.confirm(`确定删除身份源「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteAuthProvider(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(load)
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
.mask {
  color: var(--el-text-color-secondary);
  font-family: monospace;
}
.hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
