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

    <el-dialog v-model="editorVisible" :title="editingId ? '编辑身份源' : '新增身份源'" width="620px">
      <el-form :model="form" label-width="140px">
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

        <template v-if="form.type === 'ldap'">
          <el-form-item label="server_uri">
            <el-input v-model="ldap.server_uri" placeholder="ldaps://ldap.example.com:636" />
          </el-form-item>
          <el-form-item label="bind_dn_template">
            <el-input v-model="ldap.bind_dn_template" placeholder="uid={username},ou=people,dc=example,dc=com" />
          </el-form-item>
          <el-form-item label="base_dn">
            <el-input v-model="ldap.base_dn" placeholder="ou=people,dc=example,dc=com" />
          </el-form-item>
          <el-form-item label="filter">
            <el-input v-model="ldap.filter" placeholder="(objectClass=person)" />
          </el-form-item>
          <el-form-item label="map_key">
            <el-select v-model="ldap.map_key" style="width: 100%">
              <el-option v-for="k in ldapMapKeys" :key="k" :label="k" :value="k" />
            </el-select>
          </el-form-item>
          <el-form-item label="password">
            <el-input v-model="ldap.password" type="password" show-password :placeholder="secretPlaceholder" />
          </el-form-item>
        </template>

        <template v-else>
          <el-form-item label="authorization_endpoint">
            <el-input v-model="oauth.authorization_endpoint" placeholder="https://idp.example.com/oauth/authorize" />
          </el-form-item>
          <el-form-item label="token_endpoint">
            <el-input v-model="oauth.token_endpoint" placeholder="https://idp.example.com/oauth/token" />
          </el-form-item>
          <el-form-item label="client_id">
            <el-input v-model="oauth.client_id" />
          </el-form-item>
          <el-form-item label="client_secret">
            <el-input v-model="oauth.client_secret" type="password" show-password :placeholder="secretPlaceholder" />
          </el-form-item>
          <el-form-item label="redirect_uri">
            <el-input v-model="oauth.redirect_uri" placeholder="https://<backend>/api/v1/auth/oauth/<code>/callback" />
          </el-form-item>
          <el-form-item label="scope">
            <el-input v-model="oauth.scope" placeholder="openid profile email" />
          </el-form-item>
          <el-form-item label="userinfo_endpoint">
            <el-input v-model="oauth.userinfo_endpoint" placeholder="https://idp.example.com/oauth/userinfo" />
          </el-form-item>
          <el-form-item label="map_key">
            <el-select v-model="oauth.map_key" style="width: 100%">
              <el-option v-for="k in oauthMapKeys" :key="k" :label="k" :value="k" />
            </el-select>
          </el-form-item>
          <el-form-item label="roles_claim">
            <el-input v-model="oauth.roles_claim" placeholder="roles" />
          </el-form-item>
        </template>

        <el-form-item label="auto_provision">
          <el-switch v-model="configBool.auto_provision" :active-value="true" :inactive-value="false" />
        </el-form-item>
        <el-form-item label="default_role_codes">
          <el-select
            v-model="configBool.default_role_codes"
            multiple
            filterable
            allow-create
            default-first-option
            style="width: 100%"
            placeholder="选择/输入角色码（不得含 admin）"
          >
            <el-option v-for="r in roles" :key="r.code" :label="`${r.name} (${r.code})`" :value="r.code" />
          </el-select>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createAuthProvider,
  deleteAuthProvider,
  listAuthProviders,
  setAuthProviderStatus,
  testAuthProvider,
  updateAuthProvider,
} from '../../api/authProviders'
import { listRoles } from '../../api/system'
import type { AuthProviderOut, AuthProviderType, RoleOut } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const saving = ref(false)
const testingId = ref<number | null>(null)
const rows = ref<AuthProviderOut[]>([])
const roles = ref<RoleOut[]>([])

const ldapMapKeys = ['username', 'email', 'uid']
const oauthMapKeys = ['sub', 'preferred_username', 'email', 'username', 'uid']

const editorVisible = ref(false)
const editingId = ref<number | null>(null)
const secretPlaceholder = computed(() => (editingId.value ? '留空＝保留原密钥' : ''))

const ldap = reactive({
  server_uri: '',
  bind_dn_template: '',
  base_dn: '',
  filter: '',
  map_key: 'email',
  password: '',
})

const oauth = reactive({
  authorization_endpoint: '',
  token_endpoint: '',
  client_id: '',
  client_secret: '',
  redirect_uri: '',
  scope: '',
  userinfo_endpoint: '',
  map_key: 'email',
  roles_claim: '',
})

const configBool = reactive({
  auto_provision: false,
  default_role_codes: [] as string[],
})

const form = reactive({
  name: '',
  code: '',
  type: 'ldap' as AuthProviderType,
  enabled: 1,
})

function resetConfig() {
  Object.assign(ldap, { server_uri: '', bind_dn_template: '', base_dn: '', filter: '', map_key: 'email', password: '' })
  Object.assign(oauth, {
    authorization_endpoint: '',
    token_endpoint: '',
    client_id: '',
    client_secret: '',
    redirect_uri: '',
    scope: '',
    userinfo_endpoint: '',
    map_key: 'email',
    roles_claim: '',
  })
  configBool.auto_provision = false
  configBool.default_role_codes = []
}

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
  resetConfig()
  editorVisible.value = true
}

function openEdit(row: AuthProviderOut) {
  editingId.value = row.id
  Object.assign(form, { name: row.name, code: row.code, type: row.type, enabled: row.enabled })
  resetConfig()
  const mask = (row.config_mask || {}) as Record<string, unknown>
  if (row.type === 'ldap') {
    for (const k of ['server_uri', 'bind_dn_template', 'base_dn', 'filter', 'map_key'] as const) {
      if (typeof mask[k] === 'string') (ldap as Record<string, unknown>)[k] = mask[k]
    }
  } else {
    for (const k of ['authorization_endpoint', 'token_endpoint', 'client_id', 'redirect_uri', 'scope', 'userinfo_endpoint', 'map_key', 'roles_claim'] as const) {
      if (typeof mask[k] === 'string') (oauth as Record<string, unknown>)[k] = mask[k]
    }
  }
  if (typeof mask.auto_provision === 'boolean') configBool.auto_provision = mask.auto_provision
  if (Array.isArray(mask.default_role_codes)) {
    configBool.default_role_codes = (mask.default_role_codes as string[]).slice()
  }
  editorVisible.value = true
}

function buildConfig(): Record<string, unknown> {
  const base: Record<string, unknown> = {
    auto_provision: configBool.auto_provision,
    default_role_codes: configBool.default_role_codes,
  }
  if (form.type === 'ldap') {
    const cfg: Record<string, unknown> = {
      ...base,
      server_uri: ldap.server_uri,
      bind_dn_template: ldap.bind_dn_template,
      base_dn: ldap.base_dn,
      filter: ldap.filter,
      map_key: ldap.map_key,
    }
    if (ldap.password) cfg.password = ldap.password
    return cfg
  }
  const cfg: Record<string, unknown> = {
    ...base,
    authorization_endpoint: oauth.authorization_endpoint,
    token_endpoint: oauth.token_endpoint,
    client_id: oauth.client_id,
    redirect_uri: oauth.redirect_uri,
    scope: oauth.scope,
    userinfo_endpoint: oauth.userinfo_endpoint,
    map_key: oauth.map_key,
    roles_claim: oauth.roles_claim,
  }
  if (oauth.client_secret) cfg.client_secret = oauth.client_secret
  return cfg
}

async function onSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写名称')
    return
  }
  const config = buildConfig()
  saving.value = true
  try {
    if (editingId.value) {
      await updateAuthProvider(editingId.value, { name: form.name, enabled: form.enabled, config })
    } else {
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

onMounted(async () => {
  roles.value = await listRoles().catch(() => [])
  load()
})
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
</style>
