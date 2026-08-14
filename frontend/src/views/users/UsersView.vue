<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">用户管理</span>
          <el-button type="primary" v-perm="'system:user:add'" @click="openCreate">新增用户</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load">
        <el-form-item label="用户名">
          <el-input v-model="query.username" clearable placeholder="模糊搜索" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 110px">
            <el-option label="启用" :value="1" />
            <el-option label="禁用" :value="0" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="real_name" label="姓名" min-width="100" />
        <el-table-column prop="email" label="邮箱" min-width="150" />
        <el-table-column prop="phone" label="手机" min-width="120" />
        <el-table-column label="角色" min-width="140">
          <template #default="{ row }">
            <el-tag v-for="r in roleMap.get(row.id) || []" :key="r.id" size="small" style="margin-right: 4px">
              {{ r.name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 1 ? 'success' : 'danger'">
              {{ row.status === 1 ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login_at" label="最后登录" width="170">
          <template #default="{ row }">
            {{ row.last_login_at ? new Date(row.last_login_at).toLocaleString() : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'system:user:edit'" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" v-perm="'system:user:role'" @click="openRoles(row)">角色</el-button>
            <el-button size="small" v-perm="'system:user:edit'" @click="openResetPwd(row)">重置密码</el-button>
            <el-button size="small" type="danger" v-perm="'system:user:del'" @click="onDelete(row)">删除</el-button>
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
        @change="load"
      />
    </el-card>

    <el-dialog v-model="editorVisible" :title="editingId ? '编辑用户' : '新增用户'" width="480px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名" v-if="!editingId">
          <el-input v-model="form.username" :maxlength="64" />
        </el-form-item>
        <el-form-item label="密码" v-if="!editingId">
          <el-input v-model="form.password" type="password" show-password :maxlength="128" />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="form.real_name" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="form.email" />
        </el-form-item>
        <el-form-item label="手机">
          <el-input v-model="form.phone" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role_ids" multiple style="width: 100%">
            <el-option v-for="r in roles" :key="r.id" :label="`${r.name} (${r.code})`" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="form.status">
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

    <el-dialog v-model="rolesVisible" title="分配角色" width="420px">
      <el-select v-model="selectedRoleIds" multiple style="width: 100%" placeholder="选择角色">
        <el-option v-for="r in roles" :key="r.id" :label="`${r.name} (${r.code})`" :value="r.id" />
      </el-select>
      <template #footer>
        <el-button @click="rolesVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveRoles">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="pwdVisible" title="重置密码" width="420px">
      <el-form :model="pwdForm" label-width="80px">
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.password" type="password" show-password :maxlength="128" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSavePwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createUser,
  deleteUser,
  listRoles,
  listUsers,
  resetPassword,
  setUserRoles,
  updateUser,
  type UserListQuery,
} from '../../api/system'
import type { RoleBrief, UserOut } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const saving = ref(false)
const rows = ref<UserOut[]>([])
const total = ref(0)
const roles = ref<RoleBrief[]>([])
const roleMap = ref(new Map<number, RoleBrief[]>())

const query = reactive<UserListQuery>({ page: 1, size: 10 })

const editorVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  username: '',
  password: '',
  real_name: '',
  email: '',
  phone: '',
  role_ids: [] as number[],
  status: 1,
})

const rolesVisible = ref(false)
const selectedRoleIds = ref<number[]>([])
const currentUser = ref<UserOut | null>(null)

const pwdVisible = ref(false)
const pwdForm = reactive({ password: '' })

async function load() {
  loading.value = true
  try {
    const page = await listUsers(query)
    rows.value = page.list
    total.value = page.total
    const map = new Map<number, RoleBrief[]>()
    for (const u of page.list) {
      map.set(u.id, (u.role_ids ?? []).map((rid) => roles.value.find((r) => r.id === rid)).filter(Boolean) as RoleBrief[])
    }
    roleMap.value = map
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.username = undefined
  query.status = undefined
  query.page = 1
  load()
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { username: '', password: '', real_name: '', email: '', phone: '', role_ids: [], status: 1 })
  editorVisible.value = true
}

function openEdit(row: UserOut) {
  editingId.value = row.id
  Object.assign(form, {
    username: row.username,
    password: '',
    real_name: row.real_name,
    email: row.email,
    phone: row.phone,
    role_ids: row.role_ids ?? [],
    status: row.status,
  })
  editorVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    if (editingId.value) {
      await updateUser(editingId.value, {
        real_name: form.real_name,
        email: form.email,
        phone: form.phone,
        status: form.status,
      })
      await setUserRoles(editingId.value, { role_ids: form.role_ids })
    } else {
      if (form.username.length < 2 || form.password.length < 6) {
        ElMessage.warning('用户名至少 2 位，密码至少 6 位')
        return
      }
      await createUser({ ...form })
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

function openRoles(row: UserOut) {
  currentUser.value = row
  selectedRoleIds.value = row.role_ids ?? []
  rolesVisible.value = true
}

async function onSaveRoles() {
  if (!currentUser.value) return
  saving.value = true
  try {
    await setUserRoles(currentUser.value.id, { role_ids: selectedRoleIds.value })
    ElMessage.success('角色已更新')
    rolesVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

function openResetPwd(row: UserOut) {
  currentUser.value = row
  pwdForm.password = ''
  pwdVisible.value = true
}

async function onSavePwd() {
  if (!currentUser.value) return
  if (pwdForm.password.length < 6) {
    ElMessage.warning('密码至少 6 位')
    return
  }
  saving.value = true
  try {
    await resetPassword(currentUser.value.id, { password: pwdForm.password })
    ElMessage.success('密码已重置')
    pwdVisible.value = false
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onDelete(row: UserOut) {
  try {
    await ElMessageBox.confirm(`确定删除用户「${row.username}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteUser(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(async () => {
  const roleResult = await listRoles().catch(() => [])
  roles.value = roleResult
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
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
