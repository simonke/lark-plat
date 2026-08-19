<template>
  <div class="groups-view">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>分组管理</span>
          <el-button type="primary" @click="showCreateDialog()" v-if="auth.hasPerm('asset:group:create')">新增分组</el-button>
        </div>
      </template>

      <el-table :data="groupTree" v-loading="loading" row-key="id" border default-expand-all :tree-props="{ children: 'children' }">
        <el-table-column prop="name" label="分组名称" min-width="200" />
        <el-table-column prop="remark" label="备注" min-width="200" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="showCreateDialog(row.id)" v-if="auth.hasPerm('asset:group:create')">新增子分组</el-button>
            <el-button size="small" @click="showEditDialog(row)" v-if="auth.hasPerm('asset:group:update')">编辑</el-button>
            <el-popconfirm title="确定删除该分组吗？" @confirm="handleDelete(row)" v-if="auth.hasPerm('asset:group:delete')">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑分组' : '新增分组'" width="450px">
      <el-form :model="form" label-width="80px" ref="formRef" :rules="rules">
        <el-form-item label="分组名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入分组名称" />
        </el-form-item>
        <el-form-item label="父分组">
          <el-tree-select v-model="form.parent_id" :data="groupTree" :props="{ label: 'name', value: 'id' }" placeholder="无（顶级分组）" clearable />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" placeholder="请输入备注" />
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
import { getGroupsTree, createGroup, updateGroup, deleteGroup } from '../../api/assets'
import type { GroupOut } from '../../api/types'
import { extractError } from '../../api/http'

const auth = useAuthStore()

const groupTree = ref<GroupOut[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(0)
const submitLoading = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ name: '', parent_id: 0, remark: '' })

const rules = {
  name: [{ required: true, message: '请输入分组名称', trigger: 'blur' }]
}

async function loadGroups() {
  loading.value = true
  try {
    groupTree.value = await getGroupsTree()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function showCreateDialog(parentId = 0) {
  isEdit.value = false
  editId.value = 0
  Object.assign(form, { name: '', parent_id: parentId, remark: '' })
  dialogVisible.value = true
}

function showEditDialog(row: GroupOut) {
  isEdit.value = true
  editId.value = row.id
  Object.assign(form, { name: row.name, parent_id: row.parent_id, remark: row.remark })
  dialogVisible.value = true
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitLoading.value = true
  try {
    if (isEdit.value) {
      await updateGroup(editId.value, { name: form.name, remark: form.remark })
      ElMessage.success('编辑成功')
    } else {
      await createGroup({ parent_id: form.parent_id, name: form.name })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadGroups()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    submitLoading.value = false
  }
}

async function handleDelete(row: GroupOut) {
  try {
    await deleteGroup(row.id)
    ElMessage.success('删除成功')
    loadGroups()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => {
  loadGroups()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>