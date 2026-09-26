<template>
  <el-dialog
    :model-value="modelValue"
    title="AI 生成预案（Playbook）"
    width="720px"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="AI 仅生成建议草案，需人工采纳并创建；执行仍走既有审批/编排引擎"
      class="hint"
    />

    <el-form label-width="90px">
      <el-form-item label="目标">
        <el-input v-model="goal" maxlength="256" placeholder="如：恢复 Nginx 服务" @keyup.enter="generate" />
      </el-form-item>
      <el-form-item label="上下文">
        <el-input v-model="context" type="textarea" :rows="2" maxlength="512" placeholder="可选：现象/告警/影响面" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="generating" :disabled="!goal.trim()" @click="generate">
          生成建议
        </el-button>
        <span v-if="suggestion" class="model">模型：{{ suggestion.model_name }}</span>
      </el-form-item>
    </el-form>

    <template v-if="suggestion">
      <div class="kinds">
        <span class="label">支持的 kind</span>
        <el-tag v-for="k in suggestion.supported_kinds" :key="k" size="small" effect="plain" class="kind">{{ k }}</el-tag>
      </div>
      <el-form label-width="90px">
        <el-form-item label="预案名称">
          <el-input v-model="name" maxlength="128" />
        </el-form-item>
      </el-form>
      <div class="label">草案定义 (JSON)</div>
      <el-input :model-value="definitionText" type="textarea" :rows="12" spellcheck="false" readonly />
    </template>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :loading="adopting"
        :disabled="!canAdopt"
        @click="adopt"
      >
        采用并创建
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { suggestPlaybook } from '../../api/ai'
import { createWorkflow } from '../../api/workflow'
import { extractError } from '../../api/http'
import { useAuthStore } from '../../stores/auth'
import type { PlaybookSuggestion } from '../../api/types'
import { formatDefinition, parseDefinition } from './helpers'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'created'): void
}>()

const auth = useAuthStore()
const goal = ref('')
const context = ref('')
const name = ref('')
const suggestion = ref<PlaybookSuggestion | null>(null)
const generating = ref(false)
const adopting = ref(false)

const definitionText = computed(() => formatDefinition(suggestion.value?.definition ?? null))
const canAdopt = computed(() => !!suggestion.value && name.value.trim().length > 0 && auth.hasPerm('workflow:add'))

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      goal.value = ''
      context.value = ''
      name.value = ''
      suggestion.value = null
    }
  },
)

async function generate() {
  if (!goal.value.trim()) {
    ElMessage.warning('请输入目标')
    return
  }
  generating.value = true
  try {
    const res = await suggestPlaybook({ goal: goal.value, context: context.value })
    suggestion.value = res
    name.value = res.goal || goal.value
  } catch (e) {
    suggestion.value = null
    ElMessage.warning(extractError(e))
  } finally {
    generating.value = false
  }
}

async function adopt() {
  if (!suggestion.value) return
  let definition
  try {
    definition = parseDefinition(definitionText.value)
  } catch (e) {
    ElMessage.error((e as Error).message)
    return
  }
  adopting.value = true
  try {
    await createWorkflow({
      name: name.value.trim(),
      description: `AI 预案草案（${suggestion.value.goal}）`,
      definition,
      kind: 'playbook',
    })
    ElMessage.success('已采纳并创建（需人工运行）')
    emit('update:modelValue', false)
    emit('created')
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    adopting.value = false
  }
}
</script>

<style scoped>
.hint {
  margin-bottom: 12px;
}
.model {
  margin-left: 10px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.kinds {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0 10px;
  font-size: 13px;
}
.kinds .label {
  color: var(--el-text-color-secondary);
}
.kind {
  margin-right: 2px;
}
.label {
  margin: 4px 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
