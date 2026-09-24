<template>
  <div class="page">
    <el-row :gutter="12">
      <el-col :span="6">
        <el-card>
          <template #header>
            <div class="toolbar">
              <span class="title">分类</span>
              <el-button v-perm="'kb:category:add'" size="small" @click="openCategory()">新增</el-button>
            </div>
          </template>
          <el-tree
            :data="treeData"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            default-expand-all
            highlight-current
            @node-click="onSelectCategory"
          >
            <template #default="{ data }">
              <span class="tree-node">
                <span>{{ data.name }}</span>
                <span class="tree-actions">
                  <el-button v-perm="'kb:category:edit'" link size="small" @click.stop="openCategory(data)">改</el-button>
                  <el-button v-perm="'kb:category:del'" link size="small" type="danger" @click.stop="onDeleteCategory(data)">删</el-button>
                </span>
              </span>
            </template>
          </el-tree>
        </el-card>
      </el-col>

      <el-col :span="18">
        <el-card>
          <template #header>
            <div class="toolbar">
              <span class="title">知识库{{ currentCategoryName ? ` · ${currentCategoryName}` : '' }}</span>
              <div>
                <el-button v-if="currentCategoryId" size="small" @click="clearCategory">全部分类</el-button>
                <el-button v-perm="'kb:article:add'" type="primary" size="small" @click="openCreate">新建文章</el-button>
              </div>
            </div>
          </template>

          <el-form inline @submit.prevent="load">
            <el-form-item label="关键词">
              <el-input v-model="query.keyword" clearable style="width: 180px" @keyup.enter="load" />
            </el-form-item>
            <el-form-item label="可见级">
              <el-select v-model="query.visibility" clearable placeholder="全部" style="width: 120px">
                <el-option v-for="v in visibilityOptions" :key="v.value" :label="v.label" :value="v.value" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="load">查询</el-button>
            </el-form-item>
          </el-form>

          <el-table :data="rows" v-loading="loading" border @row-click="openArticle">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
            <el-table-column label="可见级" width="90">
              <template #default="{ row }">
                <el-tag :type="visibilityTag(row.visibility)" size="small">{{ visibilityLabel(row.visibility) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="版本" width="70">
              <template #default="{ row }">v{{ row.current_version }}</template>
            </el-table-column>
            <el-table-column label="更新时间" width="170">
              <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90" fixed="right">
              <template #default="{ row }">
                <el-button size="small" @click.stop="openArticle(row)">查看</el-button>
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
      </el-col>
    </el-row>

    <el-dialog v-model="createVisible" title="新建文章" width="560px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="标题"><el-input v-model="form.title" :maxlength="256" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category_id" clearable style="width: 100%">
            <el-option v-for="c in flatCategories" :key="c.id" :label="c.label" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="可见级">
          <el-select v-model="form.visibility" style="width: 100%">
            <el-option v-for="v in visibilityOptions" :key="v.value" :label="v.label" :value="v.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="摘要"><el-input v-model="form.summary" :maxlength="256" /></el-form-item>
        <el-form-item label="内容">
          <el-input v-model="form.content" type="textarea" :rows="8" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreate">提交</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="categoryVisible" :title="categoryForm.id ? '编辑分类' : '新增分类'" width="420px">
      <el-form :model="categoryForm" label-width="80px">
        <el-form-item label="名称"><el-input v-model="categoryForm.name" :maxlength="128" /></el-form-item>
        <el-form-item label="上级分类">
          <el-select v-model="categoryForm.parent_id" clearable placeholder="顶级分类" style="width: 100%">
            <el-option v-for="c in flatCategories" :key="c.id" :label="c.label" :value="c.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="categoryVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveCategory">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listArticles,
  createArticle,
  listCategories,
  createCategory,
  updateCategory,
  deleteCategory,
} from '../../api/kb'
import type {
  KbArticleOut,
  KbArticleQuery,
  KbArticleCreate,
  KbCategoryNode,
  KbVisibility,
} from '../../api/types'
import { extractError } from '../../api/http'

const router = useRouter()
const loading = ref(false)
const saving = ref(false)
const rows = ref<KbArticleOut[]>([])
const total = ref(0)
const query = reactive<KbArticleQuery>({ page: 1, size: 10 })

const visibilityOptions = [
  { value: 'public', label: '公开' },
  { value: 'internal', label: '内部' },
  { value: 'classified', label: '机密' },
]

function visibilityLabel(v: string): string {
  return visibilityOptions.find((o) => o.value === v)?.label ?? v
}
function visibilityTag(v: string): string {
  return v === 'classified' ? 'danger' : v === 'public' ? 'success' : 'info'
}
function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

const treeData = ref<KbCategoryNode[]>([])
const currentCategoryId = ref<number | null>(null)
const currentCategoryName = ref('')

const flatCategories = computed(() => {
  const out: { id: number; label: string }[] = []
  const walk = (nodes: KbCategoryNode[], prefix: string) => {
    nodes.forEach((n) => {
      out.push({ id: n.id, label: `${prefix}${n.name}` })
      if (n.children?.length) walk(n.children, `${prefix}${n.name} / `)
    })
  }
  walk(treeData.value, '')
  return out
})

async function loadCategories() {
  try {
    const res = await listCategories()
    treeData.value = res.tree
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

function onSelectCategory(data: KbCategoryNode) {
  currentCategoryId.value = data.id
  currentCategoryName.value = data.name
  query.category_id = data.id
  query.page = 1
  load()
}

function clearCategory() {
  currentCategoryId.value = null
  currentCategoryName.value = ''
  query.category_id = undefined
  query.page = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const page = await listArticles({ ...query })
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function openArticle(row: KbArticleOut) {
  router.push(`/kb/articles/${row.id}`)
}

// ---- create article
const createVisible = ref(false)
const form = reactive<KbArticleCreate>({
  title: '',
  category_id: null,
  visibility: 'internal',
  content: '',
  summary: '',
})

function openCreate() {
  form.title = ''
  form.category_id = currentCategoryId.value
  form.visibility = 'internal'
  form.content = ''
  form.summary = ''
  createVisible.value = true
}

async function onCreate() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('标题与内容必填')
    return
  }
  saving.value = true
  try {
    await createArticle({
      title: form.title,
      category_id: form.category_id ?? null,
      visibility: form.visibility as KbVisibility,
      content: form.content,
      summary: form.summary,
    })
    ElMessage.success('已创建')
    createVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

// ---- category management
const categoryVisible = ref(false)
const categoryForm = reactive<{ id: number | null; name: string; parent_id: number | null }>({
  id: null,
  name: '',
  parent_id: null,
})

function openCategory(node?: KbCategoryNode) {
  if (node) {
    categoryForm.id = node.id
    categoryForm.name = node.name
    categoryForm.parent_id = node.parent_id || null
  } else {
    categoryForm.id = null
    categoryForm.name = ''
    categoryForm.parent_id = null
  }
  categoryVisible.value = true
}

async function onSaveCategory() {
  if (!categoryForm.name.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    if (categoryForm.id) {
      await updateCategory(categoryForm.id, {
        name: categoryForm.name,
        parent_id: categoryForm.parent_id ?? 0,
      })
    } else {
      await createCategory({
        name: categoryForm.name,
        parent_id: categoryForm.parent_id ?? 0,
      })
    }
    ElMessage.success('已保存')
    categoryVisible.value = false
    loadCategories()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

async function onDeleteCategory(node: KbCategoryNode) {
  try {
    await ElMessageBox.confirm(`确定删除分类「${node.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteCategory(node.id)
    ElMessage.success('已删除')
    if (currentCategoryId.value === node.id) clearCategory()
    loadCategories()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => {
  loadCategories()
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
.tree-node {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.tree-actions {
  display: none;
}
.tree-node:hover .tree-actions {
  display: inline-block;
}
</style>
