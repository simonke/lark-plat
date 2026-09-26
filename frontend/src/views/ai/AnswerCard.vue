<template>
  <EvidenceCard
    title="AI 回答"
    :model-name="result?.model_name"
    :authoritative="result?.authoritative ?? false"
    :hitl="true"
  >
    <template v-if="failClosed">
      <el-empty description="AI 未启用或当前范围内无依据" :image-size="60" />
    </template>
    <template v-else-if="result">
      <div class="answer">{{ result.answer }}</div>
      <div v-if="result.citations.length" class="citations">
        <div class="citations-title">依据（可点回源）</div>
        <el-tag
          v-for="c in result.citations"
          :key="c.chunk_ref"
          :class="['citation', { 'citation-off': !reachable(c) }]"
          size="small"
          :type="sourceTag('kb')"
          :aria-disabled="!reachable(c)"
          :tabindex="reachable(c) ? undefined : -1"
          v-on="reachable(c) ? { click: () => openCitation(c) } : {}"
        >
          {{ c.chunk_ref }} · 相关度 {{ c.score.toFixed(3) }}
        </el-tag>
      </div>
      <div class="sink">
        <el-button v-perm="'kb:article:add'" size="small" @click="$emit('sink', result)">沉淀为 KB</el-button>
      </div>
    </template>
    <el-empty v-else description="尚未提问" :image-size="60" />
  </EvidenceCard>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import EvidenceCard from './EvidenceCard.vue'
import type { KbAnswerResult, KbCitation } from '../../api/types'
import { sourceTag, articleIdFromDocRef } from './helpers'

const props = defineProps<{ result: KbAnswerResult | null }>()
defineEmits<{ (e: 'sink', result: KbAnswerResult): void }>()

const router = useRouter()
const failClosed = computed(() => props.result?.fail_closed === true)

function reachable(c: KbCitation): boolean {
  return articleIdFromDocRef(c.doc_ref) !== null
}

function openCitation(c: KbCitation) {
  const id = articleIdFromDocRef(c.doc_ref)
  if (id !== null) router.push(`/kb/articles/${id}`)
}
</script>

<style scoped>
.answer {
  white-space: pre-wrap;
  line-height: 1.6;
}
.citations {
  margin-top: 10px;
}
.citations-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.citation {
  margin: 0 6px 6px 0;
  cursor: pointer;
}
.citation-off {
  pointer-events: none;
  opacity: 0.6;
}
.sink {
  margin-top: 10px;
}
</style>
