<template>
  <div class="page">
    <el-card>
      <div class="toolbar">
        <el-form :inline="true" @submit.prevent>
          <el-form-item label="类型">
            <el-select v-model="query.rel_type" clearable placeholder="全部" style="width: 160px" @change="load(1)">
              <el-option v-for="t in REL_TYPES" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="源 ID">
            <el-input v-model.number="query.src_id" placeholder="src_id" style="width: 120px" @keyup.enter="load(1)" />
          </el-form-item>
        </el-form>
        <el-button type="primary" v-perm="'asset:relation:add'" @click="openCreate">新建关系</el-button>
      </div>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column label="源" min-width="200">
          <template #default="{ row }">{{ entityLabel(row.src_type, row.src_id) }}</template>
        </el-table-column>
        <el-table-column label="关系" width="140">
          <template #default="{ row }">{{ relLabel(row.rel_type) }}</template>
        </el-table-column>
        <el-table-column label="目标" min-width="200">
          <template #default="{ row }">{{ entityLabel(row.dst_type, row.dst_id) }}</template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ row.created_at }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="danger" v-perm="'asset:relation:del'" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="query.size"
        :current-page="query.page"
        @current-change="load"
      />
    </el-card>

    <el-dialog v-model="createVisible" title="新建关系" width="480px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="源类型">
          <el-select v-model="form.src_type" style="width: 100%">
            <el-option v-for="t in ENTITY_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="源 ID">
          <el-input v-model.number="form.src_id" />
        </el-form-item>
        <el-form-item label="关系类型">
          <el-select v-model="form.rel_type" style="width: 100%">
            <el-option v-for="t in REL_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标类型">
          <el-select v-model="form.dst_type" style="width: 100%">
            <el-option v-for="t in ENTITY_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标 ID">
          <el-input v-model.number="form.dst_id" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" maxlength="256" show-word-limit />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreate">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getRelations, createRelation, deleteRelation } from '../../api/assets'
import { extractError } from '../../api/http'
import type { EntityRelation, RelationEntityType, CmdbRelType } from '../../api/types'

const ENTITY_TYPES: { value: RelationEntityType; label: string }[] = [
  { value: 'host', label: '主机' },
  { value: 'host_group', label: '主机分组' },
]
const REL_TYPES: { value: CmdbRelType; label: string }[] = [
  { value: 'depends_on', label: '依赖' },
  { value: 'runs_on', label: '运行于' },
  { value: 'connects_to', label: '连接' },
  { value: 'member_of', label: '属于' },
  { value: 'hosts', label: '承载' },
]

const loading = ref(false)
const saving = ref(false)
const createVisible = ref(false)
const rows = ref<EntityRelation[]>([])
const total = ref(0)

const query = reactive({ rel_type: '', src_id: undefined as number | undefined, page: 1, size: 20 })
const form = reactive({
  src_type: 'host' as RelationEntityType,
  src_id: undefined as number | undefined,
  dst_type: 'host' as RelationEntityType,
  dst_id: undefined as number | undefined,
  rel_type: 'depends_on' as CmdbRelType,
  remark: '',
})

function entityLabel(type: string, id: number) {
  return `${type === 'host' ? '主机' : '分组'} #${id}`
}
function relLabel(rel: string) {
  return REL_TYPES.find((t) => t.value === rel)?.label ?? rel
}

async function load(page = query.page) {
  query.page = page
  loading.value = true
  try {
    const res = await getRelations({
      rel_type: query.rel_type || undefined,
      src_id: query.src_id,
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

function openCreate() {
  form.src_id = undefined
  form.dst_id = undefined
  form.remark = ''
  createVisible.value = true
}

async function onCreate() {
  if (!form.src_id || !form.dst_id) {
    ElMessage.warning('请填写源/目标 ID')
    return
  }
  saving.value = true
  try {
    await createRelation({
      src_type: form.src_type,
      src_id: form.src_id!,
      dst_type: form.dst_type,
      dst_id: form.dst_id!,
      rel_type: form.rel_type,
      remark: form.remark,
    })
    ElMessage.success('已保存')
    createVisible.value = false
    await load(1)
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onDelete(row: EntityRelation) {
  try {
    await ElMessageBox.confirm(`确定删除关系 #${row.id} 吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteRelation(row.id)
    ElMessage.success('已删除')
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
  align-items: flex-start;
  margin-bottom: 12px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
</style>
