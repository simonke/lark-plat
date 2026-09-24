<template>
  <div class="page" v-loading="loading">
    <el-card>
      <template #header>
        <div class="toolbar">
          <div class="left">
            <el-button @click="goBack">返回</el-button>
            <span class="title">知识文章 #{{ articleId }}</span>
            <el-tag v-if="article" :type="visibilityTag(article.visibility)" size="small">
              {{ visibilityLabel(article.visibility) }}
            </el-tag>
            <el-tag v-if="article" type="info" size="small">v{{ article.current_version }}</el-tag>
          </div>
          <div v-if="article">
            <el-button v-perm="'kb:article:edit'" type="primary" @click="editing ? onSave() : (editing = true)">
              {{ editing ? '保存' : '编辑' }}
            </el-button>
            <el-button v-if="editing" @click="cancelEdit">取消</el-button>
            <el-button v-perm="'kb:article:del'" type="danger" plain @click="onDelete">删除</el-button>
          </div>
        </div>
      </template>

      <template v-if="article">
        <el-form :model="form" label-width="80px" v-if="editing">
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
          <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="14" /></el-form-item>
          <el-form-item label="变更说明"><el-input v-model="form.change_log" :maxlength="256" /></el-form-item>
        </el-form>

        <template v-else>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="标题" :span="2">{{ article.title }}</el-descriptions-item>
            <el-descriptions-item label="分类">{{ categoryName(article.category_id) }}</el-descriptions-item>
            <el-descriptions-item label="可见级">{{ visibilityLabel(article.visibility) }}</el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatTime(article.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ formatTime(article.updated_at) }}</el-descriptions-item>
            <el-descriptions-item label="摘要" :span="2">{{ article.summary || '-' }}</el-descriptions-item>
            <el-descriptions-item label="标签" :span="2">
              <el-tag v-for="t in article.tags" :key="t" size="small" class="tag">{{ t }}</el-tag>
              <span v-if="!article.tags.length">-</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-divider content-position="left">正文</el-divider>
          <pre class="content">{{ article.content }}</pre>
        </template>

        <el-divider content-position="left">版本历史</el-divider>
        <el-table :data="versions" border size="small">
          <el-table-column label="版本" width="80">
            <template #default="{ row }">v{{ row.version }}</template>
          </el-table-column>
          <el-table-column prop="change_log" label="变更说明" min-width="200" />
          <el-table-column label="编辑人" width="90">
            <template #default="{ row }">{{ row.editor_id ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="viewVersion(row.version)">查看</el-button>
              <el-button
                v-if="row.version !== article.current_version"
                v-perm="'kb:article:rollback'"
                size="small"
                type="warning"
                @click="onRollback(row.version)"
              >
                回滚
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>

    <el-dialog v-model="versionVisible" :title="`版本 v${versionView?.version ?? ''}`" width="640px">
      <el-descriptions :column="2" border v-if="versionView">
        <el-descriptions-item label="标题" :span="2">{{ versionView.title }}</el-descriptions-item>
        <el-descriptions-item label="变更说明" :span="2">{{ versionView.change_log || '-' }}</el-descriptions-item>
        <el-descriptions-item label="编辑人">{{ versionView.editor_id ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="时间">{{ formatTime(versionView.created_at) }}</el-descriptions-item>
      </el-descriptions>
      <pre class="content">{{ versionView?.content }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getArticle,
  updateArticle,
  deleteArticle,
  listVersions,
  getVersion,
  rollbackArticle,
  listCategories,
} from '../../api/kb'
import type {
  KbArticleDetail,
  KbArticleVersionOut,
  KbVersionOut,
  KbCategoryNode,
  KbVisibility,
} from '../../api/types'
import { extractError } from '../../api/http'

const route = useRoute()
const router = useRouter()
const articleId = Number(route.params.id)

const loading = ref(false)
const editing = ref(false)
const article = ref<KbArticleDetail | null>(null)
const versions = ref<KbArticleVersionOut[]>([])
const treeData = ref<KbCategoryNode[]>([])

const visibilityOptions = [
  { value: 'public', label: '公开' },
  { value: 'internal', label: '内部' },
  { value: 'classified', label: '机密' },
]

const form = reactive<{
  title: string
  category_id: number | null
  visibility: KbVisibility
  summary: string
  content: string
  change_log: string
}>({ title: '', category_id: null, visibility: 'internal', summary: '', content: '', change_log: '' })

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

function visibilityLabel(v: string): string {
  return visibilityOptions.find((o) => o.value === v)?.label ?? v
}
function visibilityTag(v: string): string {
  return v === 'classified' ? 'danger' : v === 'public' ? 'success' : 'info'
}
function categoryName(id: number | null): string {
  if (!id) return '-'
  return flatCategories.value.find((c) => c.id === id)?.label ?? `#${id}`
}
function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

function fillForm(a: KbArticleDetail) {
  form.title = a.title
  form.category_id = a.category_id
  form.visibility = a.visibility as KbVisibility
  form.summary = a.summary
  form.content = a.content
  form.change_log = ''
}

async function load() {
  loading.value = true
  try {
    article.value = await getArticle(articleId)
    fillForm(article.value)
    const vres = await listVersions(articleId)
    versions.value = vres.list
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try {
    const res = await listCategories()
    treeData.value = res.tree
  } catch {
    treeData.value = []
  }
}

function cancelEdit() {
  editing.value = false
  if (article.value) fillForm(article.value)
}

async function onSave() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('标题与内容必填')
    return
  }
  loading.value = true
  try {
    await updateArticle(articleId, {
      title: form.title,
      category_id: form.category_id ?? null,
      visibility: form.visibility,
      summary: form.summary,
      content: form.content,
      change_log: form.change_log,
    })
    ElMessage.success('已保存（生成新版本）')
    editing.value = false
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function onRollback(version: number) {
  try {
    await ElMessageBox.confirm(`确定回滚到 v${version} 吗？（将生成新版本）`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await rollbackArticle(articleId, version)
    ElMessage.success('已回滚')
    await load()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const versionVisible = ref(false)
const versionView = ref<KbVersionOut | null>(null)

async function viewVersion(version: number) {
  try {
    versionView.value = await getVersion(articleId, version)
    versionVisible.value = true
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function onDelete() {
  try {
    await ElMessageBox.confirm('确定删除该文章吗？被工单引用时将被拒绝。', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteArticle(articleId)
    ElMessage.success('已删除')
    router.push('/kb/articles')
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

function goBack() {
  router.push('/kb/articles')
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
.content {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  margin: 0;
  padding: 8px 0;
}
.tag {
  margin-right: 4px;
}
</style>
