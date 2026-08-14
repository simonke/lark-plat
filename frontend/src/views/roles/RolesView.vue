<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">角色与权限</span>
          <el-button type="primary" v-perm="'system:role:add'" @click="openCreate">新增角色</el-button>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="code" label="编码" min-width="130" />
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="remark" label="备注" min-width="160" />
        <el-table-column label="权限点" width="90">
          <template #default="{ row }">
            {{ (row.permission_ids || []).length }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'system:role:edit'" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" v-perm="'system:role:perm'" @click="openPerms(row)">分配权限</el-button>
            <el-button size="small" v-perm="'system:role:group'" @click="openGroups(row)">可见主机组</el-button>
            <el-button size="small" type="danger" v-perm="'system:role:del'" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="editorVisible" :title="editingId ? '编辑角色' : '新增角色'" width="440px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="编码" v-if="!editingId">
          <el-input v-model="form.code" :maxlength="64" placeholder="如 operator" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" :maxlength="64" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="permVisible" :title="`分配权限：${currentRole?.name || ''}`" width="520px">
      <el-tree
        ref="permTree"
        :data="permTree"
        show-checkbox
        node-key="id"
        :props="{ label: 'name', children: 'children' }"
        default-expand-all
      />
      <template #footer>
        <el-button @click="permVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSavePerms">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="groupVisible" :title="`可见主机组：${currentRole?.name || ''}`" width="520px">
      <el-alert type="info" :closable="false" title="勾选该角色可访问的主机组（数据权限，未勾选默认拒绝）" style="margin-bottom: 12px" />
      <el-tree
        ref="groupTree"
        :data="groupTree"
        show-checkbox
        node-key="id"
        :props="{ label: 'name', children: 'children' }"
        default-expand-all
      />
      <template #footer>
        <el-button @click="groupVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveGroups">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ElTree } from 'element-plus'
import {
  createRole,
  deleteRole,
  listGroupTree,
  listPermissions,
  listRoles,
  setRoleGroups,
  setRolePermissions,
  updateRole,
} from '../../api/system'
import type { GroupOut, PermissionNode, RoleOut } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const saving = ref(false)
const rows = ref<RoleOut[]>([])
const permTree = ref<PermissionNode[]>([])

const editorVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ code: '', name: '', remark: '' })

const permVisible = ref(false)
const currentRole = ref<RoleOut | null>(null)
const treeRef = ref<InstanceType<typeof ElTree> | null>(null)

const groupVisible = ref(false)
const groupTree = ref<GroupOut[]>([])
const groupTreeRef = ref<InstanceType<typeof ElTree> | null>(null)

async function load() {
  loading.value = true
  try {
    rows.value = await listRoles()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  Object.assign(form, { code: '', name: '', remark: '' })
  editorVisible.value = true
}

function openEdit(row: RoleOut) {
  editingId.value = row.id
  Object.assign(form, { code: row.code, name: row.name, remark: row.remark })
  editorVisible.value = true
}

async function onSave() {
  saving.value = true
  try {
    if (editingId.value) {
      await updateRole(editingId.value, { name: form.name, remark: form.remark })
    } else {
      if (!form.code || !form.name) {
        ElMessage.warning('编码和名称必填')
        return
      }
      await createRole({ code: form.code, name: form.name, remark: form.remark })
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

async function openPerms(row: RoleOut) {
  currentRole.value = row
  if (!permTree.value.length) {
    permTree.value = await listPermissions().catch(() => [])
  }
  permVisible.value = true
  await nextTick()
  treeRef.value?.setCheckedKeys(row.permission_ids ?? [])
}

async function onSavePerms() {
  if (!currentRole.value) return
  const checked = treeRef.value?.getCheckedKeys(true) as number[]
  saving.value = true
  try {
    await setRolePermissions(currentRole.value.id, { permission_ids: checked })
    ElMessage.success('权限已更新')
    permVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function openGroups(row: RoleOut) {
  currentRole.value = row
  if (!groupTree.value.length) {
    groupTree.value = await listGroupTree().catch(() => [])
  }
  groupVisible.value = true
  await nextTick()
  groupTreeRef.value?.setCheckedKeys(row.group_ids ?? [])
}

async function onSaveGroups() {
  if (!currentRole.value) return
  const checked = groupTreeRef.value?.getCheckedKeys(true) as number[]
  saving.value = true
  try {
    await setRoleGroups(currentRole.value.id, { group_ids: checked })
    ElMessage.success('主机组已更新')
    groupVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onDelete(row: RoleOut) {
  try {
    await ElMessageBox.confirm(`确定删除角色「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteRole(row.id)
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
</style>
