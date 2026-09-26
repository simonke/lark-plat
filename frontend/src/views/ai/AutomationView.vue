<template>
  <div class="page">
    <el-alert
      v-if="featureOff"
      type="warning"
      :closable="false"
      show-icon
      title="受控自动处置未启用（flag ai.auto_remediate 关闭）"
      description="开关关闭时后端按 feature-first 返回 400/403，页面仅展示空态；开启后再试。"
    />

    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">自动化等级（受控自动处置 L4）</span>
          <el-tag size="small" type="info" effect="plain">AI 输出非权威·写操作仍经 exec+approval</el-tag>
        </div>
      </template>
      <div class="level">
        <span>当前等级：</span>
        <el-tag size="small" :type="currentTag">{{ level?.current || '—' }}</el-tag>
        <span class="hint">最高启用 {{ AUTOMATION_MAX_LEVEL }}（本阶段不进入 L5 自愈）</span>
        <template v-if="canAdmin">
          <el-select v-model="levelDraft" style="width: 110px">
            <el-option v-for="l in AUTOMATION_LEVELS" :key="l" :label="l" :value="l" />
          </el-select>
          <el-button type="primary" :loading="savingLevel" @click="onSaveLevel">保存等级</el-button>
        </template>
      </div>
      <el-table :data="level?.matrix || []" size="small" border class="spaced" v-loading="loadingLevel">
        <el-table-column prop="level" label="等级" width="90" />
        <el-table-column prop="capability" label="能力 / 授权" min-width="240" show-overflow-tooltip />
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="spaced">
      <template #header>
        <div class="toolbar">
          <span class="title">熔断状态</span>
          <el-button link size="small" :loading="loadingCb" @click="loadCircuit">刷新</el-button>
        </div>
      </template>
      <el-descriptions :column="4" border size="small" v-loading="loadingCb">
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="circuitStateTag(cb?.state)">{{ circuitStateLabel(cb?.state) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="阈值">{{ cb?.threshold ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="当前值">{{ cb?.current ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="最近熔断">{{ formatTime(cb?.last_tripped_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="spaced">
      <template #header>
        <div class="toolbar">
          <span class="title">白名单（仅白名单内低风险可自动）</span>
          <el-button v-if="canAdmin" type="primary" size="small" @click="openCreate">新增白名单</el-button>
        </div>
      </template>
      <el-form inline @submit.prevent="onSearch">
        <el-form-item label="动作">
          <el-input v-model="wq.action" clearable style="width: 180px" />
        </el-form-item>
        <el-form-item label="启用">
          <el-select v-model="wq.enabled" clearable placeholder="全部" style="width: 110px">
            <el-option label="启用" :value="true" />
            <el-option label="停用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button @click="onSearch">查询</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="rows" v-loading="loadingWhitelist" border size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="action" label="动作" min-width="160" show-overflow-tooltip />
        <el-table-column label="风险" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="riskTag(row.risk_level)">{{ riskLabel(row.risk_level) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.enabled ? 'success' : 'info'" effect="plain">
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新人" width="90">
          <template #default="{ row }">{{ row.updated_by ?? '-' }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column v-if="canAdmin" label="操作" width="190">
          <template #default="{ row }">
            <el-button link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link size="small" @click="onToggle(row)">{{ row.enabled ? '停用' : '启用' }}</el-button>
            <el-button link type="danger" size="small" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pager"
        layout="total, prev, pager, next"
        :total="total"
        v-model:current-page="wq.page"
        v-model:page-size="wq.size"
        @change="loadWhitelist"
      />
    </el-card>

    <el-card class="spaced">
      <template #header>
        <span class="title">自动处置预演（dry-run · 只读零副作用）</span>
      </template>
      <el-form inline @submit.prevent="runDryRun">
        <el-form-item label="动作">
          <el-input v-model="dry.action" clearable placeholder="如 restart_service" style="width: 200px" />
        </el-form-item>
        <el-form-item label="目标">
          <el-input v-model="dry.target" clearable placeholder="host#10.0.0.1" style="width: 220px" />
        </el-form-item>
        <el-form-item>
          <el-button :loading="dryLoading" @click="runDryRun">预演</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="预演不写任何目标系统，仅落一条 dry_run 审计行（可回溯）"
      />
      <el-table v-if="dryResult" :data="dryResult.items" size="small" border class="spaced-sm">
        <el-table-column label="目标" min-width="160">
          <template #default="{ row }">{{ row.target || '—' }}</template>
        </el-table-column>
        <el-table-column prop="expected_effect" label="预期效果" min-width="220" show-overflow-tooltip />
        <el-table-column label="风险" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="riskTag(row.risk_level)">{{ riskLabel(row.risk_level) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="dryResult" class="hint">
        writable: {{ dryResult.writable }} · idempotency_key: {{ dryResult.idempotency_key }}
      </div>
    </el-card>

    <el-card v-if="canAdmin" class="spaced">
      <template #header>
        <span class="title">处置运行回滚</span>
      </template>
      <el-form inline @submit.prevent="runRollback">
        <el-form-item label="运行 ID">
          <el-input v-model.number="rollbackRunId" type="number" style="width: 160px" />
        </el-form-item>
        <el-form-item>
          <el-button type="danger" plain :loading="rollbackLoading" @click="runRollback">回滚</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="rollbackResult"
        :type="rollbackResult.status === 'rolled_back' ? 'success' : 'warning'"
        :closable="false"
        show-icon
        :title="rollbackResult.status === 'rolled_back' ? '已回滚' : '不可回滚'"
        :description="rollbackResult.reason || ''"
      />
      <div class="hint">回滚经既有 exec+approval 原语派发；重复回滚为幂等（同终态、不重复补偿）。</div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑白名单' : '新增白名单'" width="440px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="动作">
          <el-input v-model="form.action" :disabled="editing" />
        </el-form-item>
        <el-form-item label="风险等级">
          <el-select v-model="form.risk_level" style="width: 140px">
            <el-option v-for="r in RISK_LEVELS" :key="r" :label="riskLabel(r)" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <div class="hint">仅 risk_level=low 的动作可在 L4 自动执行；medium 需人工确认、high 禁自动。</div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="dialogLoading" @click="onSubmit">
          {{ editing ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import {
  getAutomationLevel,
  setAutomationLevel,
  listAutomationWhitelist,
  createAutomationWhitelist,
  updateAutomationWhitelist,
  deleteAutomationWhitelist,
  automationDryRun,
  rollbackAutomationRun,
  getCircuitBreaker,
} from '../../api/automation'
import { extractError } from '../../api/http'
import type {
  AutomationLevel,
  AutomationRiskLevel,
  AutomationRollbackResult,
  AutomationWhitelistItem,
  AutomationWhitelistQuery,
  CircuitBreakerState,
  DryRunResult,
} from '../../api/types'
import {
  AUTOMATION_LEVELS,
  AUTOMATION_MAX_LEVEL,
  RISK_LEVELS,
  riskLabel,
  riskTag,
  circuitStateLabel,
  circuitStateTag,
  buildDryRunKey,
} from './helpers'

const auth = useAuthStore()
const canAdmin = computed(() => auth.hasPerm('ai:admin'))

const featureOff = ref(false)

// ---- level
const level = ref<AutomationLevel | null>(null)
const levelDraft = ref('')
const loadingLevel = ref(false)
const savingLevel = ref(false)
const currentTag = computed(() => (level.value?.current === AUTOMATION_MAX_LEVEL ? 'warning' : 'success'))

// ---- circuit breaker
const cb = ref<CircuitBreakerState | null>(null)
const loadingCb = ref(false)

// ---- whitelist
const rows = ref<AutomationWhitelistItem[]>([])
const total = ref(0)
const loadingWhitelist = ref(false)
const wq = reactive<AutomationWhitelistQuery>({ page: 1, size: 10 })

const dialogVisible = ref(false)
const editing = ref(false)
const dialogLoading = ref(false)
const form = reactive<{ id: number | null; action: string; risk_level: AutomationRiskLevel; enabled: boolean }>({
  id: null,
  action: '',
  risk_level: 'low',
  enabled: true,
})

// ---- dry-run
const dry = reactive({ action: '', target: '' })
const dryLoading = ref(false)
const dryResult = ref<DryRunResult | null>(null)

// ---- rollback
const rollbackRunId = ref<number | null>(null)
const rollbackLoading = ref(false)
const rollbackResult = ref<AutomationRollbackResult | null>(null)

function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

async function loadLevel() {
  loadingLevel.value = true
  try {
    level.value = await getAutomationLevel()
    levelDraft.value = level.value.current
    featureOff.value = false
  } catch (e) {
    featureOff.value = true
    level.value = null
    ElMessage.warning(extractError(e))
  } finally {
    loadingLevel.value = false
  }
}

async function onSaveLevel() {
  if (!levelDraft.value || levelDraft.value === level.value?.current) {
    ElMessage.info('等级未变化')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将自动化等级切换为 ${levelDraft.value}？此操作会写入审计。`,
      '二次确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  savingLevel.value = true
  try {
    level.value = await setAutomationLevel(levelDraft.value)
    ElMessage.success('等级已更新')
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    savingLevel.value = false
  }
}

async function loadCircuit() {
  loadingCb.value = true
  try {
    cb.value = await getCircuitBreaker()
  } catch (e) {
    cb.value = null
    ElMessage.warning(extractError(e))
  } finally {
    loadingCb.value = false
  }
}

async function loadWhitelist() {
  loadingWhitelist.value = true
  try {
    const page = await listAutomationWhitelist({ ...wq })
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    rows.value = []
    total.value = 0
    ElMessage.warning(extractError(e))
  } finally {
    loadingWhitelist.value = false
  }
}

function onSearch() {
  wq.page = 1
  loadWhitelist()
}

function openCreate() {
  editing.value = false
  form.id = null
  form.action = ''
  form.risk_level = 'low'
  form.enabled = true
  dialogVisible.value = true
}

function openEdit(row: AutomationWhitelistItem) {
  editing.value = true
  form.id = row.id
  form.action = row.action
  form.risk_level = row.risk_level
  form.enabled = row.enabled
  dialogVisible.value = true
}

async function onSubmit() {
  if (!form.action.trim()) {
    ElMessage.warning('请输入动作')
    return
  }
  dialogLoading.value = true
  try {
    if (editing.value && form.id !== null) {
      await updateAutomationWhitelist(form.id, { risk_level: form.risk_level, enabled: form.enabled })
      ElMessage.success('已更新')
    } else {
      await createAutomationWhitelist({
        action: form.action.trim(),
        risk_level: form.risk_level,
        enabled: form.enabled,
      })
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    loadWhitelist()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    dialogLoading.value = false
  }
}

async function onToggle(row: AutomationWhitelistItem) {
  try {
    await updateAutomationWhitelist(row.id, { enabled: !row.enabled })
    ElMessage.success('已更新')
    loadWhitelist()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function onDelete(row: AutomationWhitelistItem) {
  try {
    await ElMessageBox.confirm(`删除白名单「${row.action}」？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteAutomationWhitelist(row.id)
    ElMessage.success('已删除')
    loadWhitelist()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function runDryRun() {
  dryLoading.value = true
  try {
    dryResult.value = await automationDryRun({
      idempotency_key: buildDryRunKey(dry.action),
      action: dry.action || null,
      target: dry.target || null,
    })
    if (!dryResult.value.items.length) ElMessage.info('无预演动作（仅记录一条 dry_run 审计行）')
  } catch (e) {
    dryResult.value = null
    ElMessage.error(extractError(e))
  } finally {
    dryLoading.value = false
  }
}

async function runRollback() {
  if (!rollbackRunId.value) {
    ElMessage.warning('请输入运行 ID')
    return
  }
  rollbackLoading.value = true
  try {
    rollbackResult.value = await rollbackAutomationRun(rollbackRunId.value)
  } catch (e) {
    rollbackResult.value = null
    ElMessage.error(extractError(e))
  } finally {
    rollbackLoading.value = false
  }
}

onMounted(async () => {
  await loadLevel()
  if (!featureOff.value) {
    loadCircuit()
    loadWhitelist()
  }
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
.level {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.spaced {
  margin-top: 12px;
}
.spaced-sm {
  margin-top: 8px;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 6px;
}
</style>
