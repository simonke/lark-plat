<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">告警规则</span>
          <el-button type="primary" v-perm="'monitor:rule:add'" @click="openRule()">新增规则</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="loadRules">
        <el-form-item label="名称">
          <el-input v-model="query.name" clearable placeholder="规则名" style="width: 180px" />
        </el-form-item>
        <el-form-item label="事件类型">
          <el-select v-model="query.event_kind" clearable placeholder="全部" style="width: 130px">
            <el-option label="指标" value="metric" />
            <el-option label="告警" value="alert" />
            <el-option label="日志" value="log" />
            <el-option label="APM" value="apm" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-select v-model="query.event_source" clearable placeholder="全部" style="width: 160px">
            <el-option v-for="s in sources" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadRules">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rules" v-loading="loading" border>
        <el-table-column prop="name" label="规则名" min-width="150" show-overflow-tooltip />
        <el-table-column label="事件" width="110">
          <template #default="{ row }">
            <el-tag size="small">{{ kindLabel(row.event_kind) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="130">
          <template #default="{ row }">
            <span>{{ sourceLabel(row.event_source) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="条件" min-width="180">
          <template #default="{ row }">
            <code>{{ ruleConditionText(row) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="收敛" width="90">
          <template #default="{ row }">
            <span>{{ row.cooldown_seconds }}s</span>
          </template>
        </el-table-column>
        <el-table-column label="升级" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.escalation_enabled" size="small" type="warning">开</el-tag>
            <span v-else>关</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'monitor:rule:edit'" @click="openRule(row)">编辑</el-button>
            <el-button size="small" v-perm="'monitor:rule:status'" @click="toggleRule(row)">
              {{ row.enabled ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" v-perm="'monitor:rule:del'" @click="onDeleteRule(row)">删除</el-button>
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
        @change="loadRules"
      />
    </el-card>

    <el-dialog v-model="ruleVisible" :title="ruleId ? '编辑规则' : '新增规则'" width="640px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="规则名" required>
          <el-input v-model="form.name" :maxlength="128" />
        </el-form-item>
        <el-form-item label="事件类型" required>
          <el-select v-model="form.event_kind" style="width: 100%" :disabled="!!ruleId">
            <el-option label="指标" value="metric" />
            <el-option label="告警" value="alert" />
            <el-option label="日志" value="log" />
            <el-option label="APM" value="apm" />
          </el-select>
        </el-form-item>
        <el-form-item label="事件来源">
          <el-select v-model="form.event_source" clearable style="width: 100%">
            <el-option v-for="s in sources" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="指标名" v-if="form.event_kind === 'metric'">
          <el-input v-model="form.metric_name" placeholder="如 cpu_usage_percent" />
        </el-form-item>
        <el-form-item label="比较符">
          <el-select v-model="form.condition_operator" style="width: 100%">
            <el-option v-for="op in operators" :key="op" :label="op" :value="op" />
          </el-select>
        </el-form-item>
        <el-form-item label="阈值" required>
          <el-input-number v-model="form.condition_threshold" :precision="2" style="width: 100%" />
        </el-form-item>
        <el-form-item label="连续时长(秒)">
          <el-input-number v-model="form.condition_duration_seconds" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="收敛窗口(秒)">
          <el-input-number v-model="form.cooldown_seconds" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="作用域类型">
          <el-select v-model="form.scope_type" clearable style="width: 100%" placeholder="全部">
            <el-option label="主机(host)" value="host" />
            <el-option label="应用(app)" value="app" />
            <el-option label="服务(service)" value="service" />
          </el-select>
        </el-form-item>
        <el-form-item label="作用域ID列表">
          <el-input v-model="scopeIdsText" placeholder="逗号分隔，如 host1,host2" />
        </el-form-item>
        <el-form-item label="告警级别">
          <el-select v-model="form.level" style="width: 100%">
            <el-option label="critical" value="critical" />
            <el-option label="warning" value="warning" />
            <el-option label="info" value="info" />
          </el-select>
        </el-form-item>
        <el-form-item label="聚合窗口(秒)">
          <el-input-number v-model="form.converge_sec" :min="0" style="width: 100%" />
        </el-form-item>
        <el-form-item label="升级级别路径">
          <el-select v-model="form.escalate_levels" multiple style="width: 100%" placeholder="可多选">
            <el-option label="info" value="info" />
            <el-option label="warning" value="warning" />
            <el-option label="critical" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="升级策略">
          <el-checkbox v-model="form.escalation_enabled">启用升级</el-checkbox>
        </el-form-item>
        <template v-if="form.escalation_enabled">
          <el-form-item label="升级延迟(秒)">
            <el-input-number v-model="form.escalation_after_seconds" :min="0" style="width: 100%" />
          </el-form-item>
          <el-form-item label="升级级别">
            <el-select v-model="form.escalation_severity" style="width: 100%">
              <el-option label="critical" value="critical" />
              <el-option label="warning" value="warning" />
              <el-option label="info" value="info" />
            </el-select>
          </el-form-item>
        </template>
        <el-form-item label="通知场景">
          <el-select v-model="form.notify_scene" style="width: 100%">
            <el-option label="alert" value="alert" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSaveRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createAlertRule,
  deleteAlertRule,
  listAlertRules,
  setRuleStatus,
  updateAlertRule,
} from '../../api/monitoring'
import type { AlertRuleOut, AlertRuleQuery, MonEventKind, MonSeverity, MonSource } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const saving = ref(false)
const rules = ref<AlertRuleOut[]>([])
const total = ref(0)
const query = reactive<AlertRuleQuery>({ page: 1, size: 10 })

const sources = [
  { label: 'Agent 自采集', value: 'agent' },
  { label: 'Prometheus', value: 'prometheus' },
  { label: 'ELK', value: 'elk' },
  { label: 'SkyWalking', value: 'skywalking' },
]
const operators = ['>', '<', '>=', '<=', '==', '!=']

const ruleVisible = ref(false)
const ruleId = ref<string | null>(null)
interface RuleForm {
  name: string
  description: string
  enabled: boolean
  event_source: MonSource | null
  event_kind: MonEventKind
  metric_name: string
  condition_operator: '>' | '<' | '>=' | '<=' | '==' | '!='
  condition_threshold: number
  condition_duration_seconds: number
  scope_type: string | null
  scope_ids: string[]
  level: string
  cooldown_seconds: number
  converge_sec: number
  escalation_enabled: boolean
  escalation_after_seconds: number
  escalation_severity: MonSeverity
  escalate_levels: string[]
  notify_scene: string
}
const form = reactive<RuleForm>({
  name: '',
  description: '',
  enabled: true,
  event_source: null,
  event_kind: 'metric',
  metric_name: '',
  condition_operator: '>',
  condition_threshold: 80,
  condition_duration_seconds: 0,
  scope_type: null,
  scope_ids: [],
  level: 'warning',
  cooldown_seconds: 300,
  converge_sec: 0,
  escalation_enabled: false,
  escalation_after_seconds: 600,
  escalation_severity: 'warning',
  escalate_levels: [],
  notify_scene: 'alert',
})

const scopeIdsText = ref('')
watch(
  () => form.scope_ids,
  (ids) => { scopeIdsText.value = (ids ?? []).join(', ') },
  { immediate: true },
)
watch(scopeIdsText, (raw) => {
  form.scope_ids = raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
})

function kindLabel(kind: string): string {
  const map: Record<string, string> = { metric: '指标', alert: '告警', log: '日志', apm: 'APM' }
  return map[kind] ?? kind
}
function sourceLabel(src: string | null): string {
  if (!src) return '全部'
  const s = sources.find((x) => x.value === src)
  return s ? s.label : src
}
function ruleConditionText(row: AlertRuleOut): string {
  const metric = row.metric_name ?? ''
  return `${metric} ${row.condition_operator} ${row.condition_threshold}`
}

async function loadRules() {
  loading.value = true
  try {
    const page = await listAlertRules(query)
    rules.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.name = undefined
  query.event_kind = undefined
  query.event_source = undefined
  query.page = 1
  loadRules()
}

function openRule(row?: AlertRuleOut) {
  if (row) {
    ruleId.value = row.id
    form.name = row.name
    form.description = row.description ?? ''
    form.enabled = row.enabled
    form.event_source = row.event_source
    form.event_kind = row.event_kind
    form.metric_name = row.metric_name ?? ''
    form.condition_operator = row.condition_operator as RuleForm['condition_operator']
    form.condition_threshold = row.condition_threshold
    form.condition_duration_seconds = row.condition_duration_seconds
    form.scope_type = row.scope_type ?? null
    form.scope_ids = row.scope_ids ? [...row.scope_ids] : []
    form.level = row.level ?? 'warning'
    form.cooldown_seconds = row.cooldown_seconds
    form.converge_sec = row.converge_sec ?? 0
    form.escalation_enabled = row.escalation_enabled
    form.escalation_after_seconds = row.escalation_after_seconds
    form.escalation_severity = row.escalation_severity
    form.escalate_levels = row.escalate_levels ? [...row.escalate_levels] : []
    form.notify_scene = row.notify_scene
  } else {
    ruleId.value = null
    form.name = ''
    form.description = ''
    form.enabled = true
    form.event_source = null
    form.event_kind = 'metric'
    form.metric_name = ''
    form.condition_operator = '>'
    form.condition_threshold = 80
    form.condition_duration_seconds = 0
    form.scope_type = null
    form.scope_ids = []
    form.level = 'warning'
    form.cooldown_seconds = 300
    form.converge_sec = 0
    form.escalation_enabled = false
    form.escalation_after_seconds = 600
    form.escalation_severity = 'warning'
    form.escalate_levels = []
    form.notify_scene = 'alert'
  }
  ruleVisible.value = true
}

async function onSaveRule() {
  if (form.name.length < 1) {
    ElMessage.warning('请输入规则名')
    return
  }
  saving.value = true
  try {
    if (ruleId.value) {
      await updateAlertRule(ruleId.value, {
        name: form.name,
        description: form.description || null,
        enabled: form.enabled,
        event_source: form.event_source ?? null,
        event_kind: form.event_kind,
        metric_name: form.metric_name || null,
        condition_operator: form.condition_operator,
        condition_threshold: form.condition_threshold,
        condition_duration_seconds: form.condition_duration_seconds,
        scope_type: form.scope_type ?? null,
        scope_ids: form.scope_ids.length ? form.scope_ids : null,
        level: form.level,
        cooldown_seconds: form.cooldown_seconds,
        converge_sec: form.converge_sec,
        escalation_enabled: form.escalation_enabled,
        escalation_after_seconds: form.escalation_after_seconds,
        escalation_severity: form.escalation_severity,
        escalate_levels: form.escalate_levels.length ? form.escalate_levels : null,
        notify_scene: form.notify_scene,
      })
    } else {
      await createAlertRule({
        name: form.name,
        description: form.description || undefined,
        enabled: form.enabled,
        event_source: form.event_source ?? null,
        event_kind: form.event_kind,
        metric_name: form.metric_name || undefined,
        condition_operator: form.condition_operator,
        condition_threshold: form.condition_threshold,
        condition_duration_seconds: form.condition_duration_seconds,
        scope_type: form.scope_type ?? undefined,
        scope_ids: form.scope_ids.length ? form.scope_ids : undefined,
        level: form.level,
        cooldown_seconds: form.cooldown_seconds,
        converge_sec: form.converge_sec,
        escalation_enabled: form.escalation_enabled,
        escalation_after_seconds: form.escalation_after_seconds,
        escalation_severity: form.escalation_severity,
        escalate_levels: form.escalate_levels.length ? form.escalate_levels : undefined,
        notify_scene: form.notify_scene,
      })
    }
    ElMessage.success('保存成功')
    ruleVisible.value = false
    loadRules()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    saving.value = false
  }
}

function toggleRule(row: AlertRuleOut) {
  setRuleStatus(row.id, !row.enabled)
    .then(() => {
      ElMessage.success('状态已更新')
      loadRules()
    })
    .catch((e) => ElMessage.error(extractError(e)))
}

async function onDeleteRule(row: AlertRuleOut) {
  try {
    await ElMessageBox.confirm(`确定删除规则「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteAlertRule(row.id)
    ElMessage.success('已删除')
    loadRules()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(loadRules)
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
