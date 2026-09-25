<template>
  <div class="page">
    <el-row :gutter="12">
      <el-col :span="7">
        <el-card>
          <template #header>
            <div class="toolbar">
              <span class="title">运维事件</span>
              <el-button size="small" :loading="loading" @click="load">刷新</el-button>
            </div>
          </template>
          <el-form inline @submit.prevent="onSearch">
            <el-form-item label="来源">
              <el-select v-model="query.source" clearable placeholder="全部" style="width: 110px">
                <el-option v-for="s in OPS_EVENT_SOURCES" :key="s" :label="sourceLabel(s)" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item label="实体">
              <el-input v-model="query.entity_type" clearable placeholder="host/ticket/kb" style="width: 130px" />
            </el-form-item>
            <el-form-item label="Trace">
              <el-input v-model="query.trace_id" clearable style="width: 150px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="onSearch">查询</el-button>
            </el-form-item>
          </el-form>

          <div class="stream" v-loading="loading">
            <div
              v-for="e in rows"
              :key="e.id"
              class="stream-item"
              :class="{ active: selected?.id === e.id }"
              @click="select(e)"
            >
              <el-tag size="small" :type="sourceTag(e.source)">{{ sourceLabel(e.source) }}</el-tag>
              <span class="summary">{{ eventSummary(e) }}</span>
              <span class="time">{{ formatTime(e.ts || e.created_at) }}</span>
            </div>
            <el-empty v-if="!rows.length && !loading" description="暂无事件" :image-size="60" />
          </div>

          <el-pagination
            class="pager"
            layout="total, prev, pager, next"
            :total="total"
            v-model:current-page="query.page"
            v-model:page-size="query.size"
            :page-sizes="[10, 20, 50]"
            @change="load"
          />
        </el-card>
      </el-col>

      <el-col :span="9">
        <el-card>
          <template #header><span class="title">事件详情</span></template>
          <template v-if="selected">
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="动作" :span="2">{{ selected.action }}</el-descriptions-item>
              <el-descriptions-item label="结果">{{ selected.result || '-' }}</el-descriptions-item>
              <el-descriptions-item label="来源">{{ sourceLabel(selected.source) }}</el-descriptions-item>
              <el-descriptions-item label="实体">{{ selected.entity_type }}#{{ selected.entity_id }}</el-descriptions-item>
              <el-descriptions-item label="时间">{{ formatTime(selected.ts || selected.created_at) }}</el-descriptions-item>
            </el-descriptions>
            <el-divider content-position="left">上下文时间线</el-divider>
            <EventTimeline :events="entityTimeline" />
          </template>
          <el-empty v-else description="选择左侧事件查看详情" />
        </el-card>
      </el-col>

      <el-col :span="8">
        <el-card class="panel">
          <template #header><span class="title">实体上下文</span></template>
          <EntityContextPanel
            :entity-type="selected?.entity_type"
            :entity-id="selected?.entity_id"
            :event-count="entityTimeline.length"
          />
          <el-divider />
          <TraceRefLink :trace-id="selected?.trace_id" :refs="selected?.refs ?? null" />
        </el-card>

        <el-card class="panel">
          <template #header>
            <div class="toolbar">
              <span class="title">AI 副驾</span>
              <el-button v-perm="'ai:use'" size="small" type="primary" :loading="aiLoading" :disabled="!selected" @click="runAi">
                在知识库中检索
              </el-button>
            </div>
          </template>
          <AnswerCard :result="aiResult" @sink="onSink" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listEvents, kbAnswer } from '../../api/ai'
import { createArticle } from '../../api/kb'
import { extractError } from '../../api/http'
import type { OpsEvent, OpsEventQuery, KbAnswerResult } from '../../api/types'
import { OPS_EVENT_SOURCES, sourceLabel, sourceTag, eventSummary } from '../ai/helpers'
import EventTimeline from './EventTimeline.vue'
import EntityContextPanel from './EntityContextPanel.vue'
import TraceRefLink from './TraceRefLink.vue'
import AnswerCard from '../ai/AnswerCard.vue'

const router = useRouter()
const loading = ref(false)
const aiLoading = ref(false)
const rows = ref<OpsEvent[]>([])
const total = ref(0)
const selected = ref<OpsEvent | null>(null)
const aiResult = ref<KbAnswerResult | null>(null)
const query = reactive<OpsEventQuery>({ page: 1, size: 20 })

const entityTimeline = computed(() => {
  if (!selected.value) return []
  return rows.value.filter(
    (e) => e.entity_type === selected.value?.entity_type && e.entity_id === selected.value?.entity_id,
  )
})

function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

function onSearch() {
  query.page = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const page = await listEvents({ ...query })
    rows.value = page.list
    total.value = page.total
    if (!selected.value && rows.value.length) {
      selected.value = rows.value[0]
    }
  } catch (e) {
    // flag off => HTTP 400 (feature-first); render 未启用 empty state rather than crash.
    rows.value = []
    total.value = 0
    ElMessage.warning(extractError(e))
  } finally {
    loading.value = false
  }
}

function select(e: OpsEvent) {
  selected.value = e
  aiResult.value = null
}

async function runAi() {
  if (!selected.value) return
  aiLoading.value = true
  try {
    aiResult.value = await kbAnswer({
      q: `${selected.value.entity_type} ${selected.value.entity_id} ${selected.value.action}`,
      limit: 5,
      entity_type: 'kb',
    })
  } catch (e) {
    aiResult.value = { answer: '', citations: [], authoritative: false, fail_closed: true }
    ElMessage.warning(extractError(e))
  } finally {
    aiLoading.value = false
  }
}

async function onSink(result: KbAnswerResult) {
  try {
    const article = await createArticle({
      title: `${selected.value?.entity_type ?? 'AI'} ${selected.value?.entity_id ?? ''} 运维沉淀`.trim(),
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
.stream {
  min-height: 200px;
  max-height: 560px;
  overflow: auto;
}
.stream-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.stream-item:hover,
.stream-item.active {
  background: var(--el-fill-color-light);
}
.summary {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.panel {
  margin-bottom: 12px;
}
</style>
