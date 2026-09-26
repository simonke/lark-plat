<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">知识助手（RAG）</span>
          <el-tag size="small" type="info" effect="plain">AI 输出非权威·仅供参考</el-tag>
        </div>
      </template>
      <el-form inline @submit.prevent="ask">
        <el-form-item label="问题">
          <el-input v-model="q" clearable placeholder="输入运维问题" style="width: 320px" @keyup.enter="ask" />
        </el-form-item>
        <el-form-item label="检索模式">
          <el-select v-model="mode" style="width: 110px">
            <el-option label="混合" value="hybrid" />
            <el-option label="向量" value="vector" />
            <el-option label="全文" value="fts" />
          </el-select>
        </el-form-item>
        <el-form-item label="域">
          <el-input v-model="entityType" clearable placeholder="kb" style="width: 120px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="asking" @click="ask">智能问答</el-button>
          <el-button :loading="searching" @click="search">语义检索</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="12" class="body">
      <el-col :span="14">
        <el-card>
          <template #header><span class="title">回答</span></template>
          <AnswerCard :result="answer" @sink="onSink" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card>
          <template #header><span class="title">检索结果</span></template>
          <el-table :data="hits" size="small" border>
            <el-table-column label="标题" min-width="160" show-overflow-tooltip>
              <template #default="{ row }">{{ row.title || '—' }}</template>
            </el-table-column>
            <el-table-column prop="chunk_ref" label="片段" min-width="180" show-overflow-tooltip />
            <el-table-column label="分支" width="80">
              <template #default="{ row }">
                <el-tag size="small" effect="plain">{{ branchLabel(row.branch) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="相关度" width="90">
              <template #default="{ row }">{{ row.score.toFixed(3) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <span :title="articleIdFromDocRef(row.doc_ref) === null ? '无法定位来源' : ''">
                  <el-button
                    link
                    size="small"
                    :disabled="articleIdFromDocRef(row.doc_ref) === null"
                    @click="openDoc(row)"
                  >
                    查看
                  </el-button>
                </span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { kbAnswer, kbSearchSemantic } from '../../api/ai'
import { createArticle } from '../../api/kb'
import { extractError } from '../../api/http'
import type { KbAnswerResult, SemanticHit } from '../../api/types'
import { branchLabel, articleIdFromDocRef } from './helpers'
import AnswerCard from './AnswerCard.vue'

const router = useRouter()
const q = ref('')
const mode = ref<'vector' | 'fts' | 'hybrid'>('hybrid')
const entityType = ref('kb')
const answer = ref<KbAnswerResult | null>(null)
const hits = ref<SemanticHit[]>([])
const asking = ref(false)
const searching = ref(false)

async function ask() {
  if (!q.value.trim()) {
    ElMessage.warning('请输入问题')
    return
  }
  asking.value = true
  try {
    answer.value = await kbAnswer({ q: q.value, entity_type: entityType.value || undefined })
  } catch (e) {
    answer.value = { answer: '', citations: [], authoritative: false, fail_closed: true }
    ElMessage.warning(extractError(e))
  } finally {
    asking.value = false
  }
}

async function search() {
  if (!q.value.trim()) {
    ElMessage.warning('请输入关键词')
    return
  }
  searching.value = true
  try {
    const res = await kbSearchSemantic({ q: q.value, mode: mode.value, entity_type: entityType.value || undefined })
    hits.value = res.list
  } catch (e) {
    hits.value = []
    ElMessage.warning(extractError(e))
  } finally {
    searching.value = false
  }
}

function openDoc(row: SemanticHit) {
  const id = articleIdFromDocRef(row.doc_ref)
  if (id !== null) router.push(`/kb/articles/${id}`)
  else ElMessage.info('该来源暂不支持跳转到文章')
}

async function onSink(result: KbAnswerResult) {
  try {
    const article = await createArticle({
      title: q.value.slice(0, 200) || 'AI 问答沉淀',
      visibility: 'internal',
      content: result.answer,
      summary: result.citations.map((c) => c.chunk_ref).join(', ').slice(0, 256),
    })
    ElMessage.success('已沉淀为知识库草稿')
    router.push(`/kb/articles/${article.id}`)
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}
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
.body {
  margin-top: 12px;
}
</style>
