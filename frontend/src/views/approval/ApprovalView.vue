<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">审批中心</span>
          <el-radio-group v-model="scope" @change="onScopeChange">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="me">我的申请</el-radio-button>
            <el-radio-button value="todo">待我处理</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load">
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 150px">
            <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="业务类型">
          <el-select v-model="query.biz_type" clearable placeholder="全部" style="width: 140px">
            <el-option label="命令执行" value="exec" />
            <el-option label="终端会话" value="terminal" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="request_no" label="单号" min-width="160" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="biz_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small">{{ bizTypeLabel(row.biz_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="sensitive_hit" label="命中规则" min-width="120" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="发起时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row.id)">详情</el-button>
            <el-button
              v-if="row.status === 'pending' && scope === 'todo'"
              size="small"
              type="success"
              @click="openDecide(row, 'approve')"
            >
              通过
            </el-button>
            <el-button
              v-if="row.status === 'pending' && scope === 'todo'"
              size="small"
              type="danger"
              @click="openDecide(row, 'reject')"
            >
              拒绝
            </el-button>
            <el-button
              v-if="row.status === 'pending' && scope === 'me'"
              size="small"
              type="warning"
              @click="openDecide(row, 'cancel')"
            >
              撤销
            </el-button>
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

    <el-card class="card-gap">
      <template #header>
        <div class="toolbar">
          <span class="title">审批规则</span>
          <el-button type="primary" v-perm="'approval:rule:add'" @click="openRule()">新建规则</el-button>
        </div>
      </template>
      <el-table :data="rules" v-loading="rulesLoading" border>
        <el-table-column prop="name" label="规则名" min-width="160" />
        <el-table-column prop="kind" label="类型" width="110">
          <template #default="{ row }">
            {{ row.kind === 'keyword' ? '关键字' : '数量阈值' }}
          </template>
        </el-table-column>
        <el-table-column label="规则值" min-width="200">
          <template #default="{ row }">
            <code>{{ JSON.stringify(row.value) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled === 1 ? 'success' : 'info'">
              {{ row.enabled === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'approval:rule:edit'" @click="openRule(row)">编辑</el-button>
            <el-button
              size="small"
              type="danger"
              v-perm="'approval:rule:del'"
              @click="onDeleteRule(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" title="审批详情" width="620px">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="单号">{{ detail.request_no }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ statusLabel(detail.status) }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ bizTypeLabel(detail.biz_type) }}</el-descriptions-item>
          <el-descriptions-item label="业务ID">{{ detail.biz_id }}</el-descriptions-item>
          <el-descriptions-item label="标题" :span="2">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="申请理由" :span="2">{{ detail.reason || '-' }}</el-descriptions-item>
          <el-descriptions-item label="命中敏感规则" :span="2">{{ detail.sensitive_hit || '-' }}</el-descriptions-item>
        </el-descriptions>
        <el-divider content-position="left">审批记录</el-divider>
        <el-timeline>
          <el-timeline-item
            v-for="(rec, i) in detail.timeline"
            :key="i"
            :timestamp="formatTime(rec.created_at)"
            :type="timelineType(rec.action)"
          >
            <b>{{ timelineAction(rec.action) }}</b>
            <span v-if="rec.comment">：{{ rec.comment }}</span>
            <span v-if="rec.operator_id">（操作人 #{{ rec.operator_id }}）</span>
          </el-timeline-item>
        </el-timeline>
      </template>
    </el-dialog>

    <el-dialog v-model="decideVisible" :title="decideTitle" width="440px">
      <el-form label-width="70px">
        <el-form-item label="意见">
          <el-input v-model="decideForm.comment" type="textarea" :rows="3" placeholder="请输入处理意见（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="decideVisible = false">取消</el-button>
        <el-button type="primary" :loading="decideLoading" @click="onDecide">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="ruleVisible" :title="ruleId ? '编辑规则' : '新建规则'" width="500px">
      <el-form :model="ruleForm" label-width="80px">
        <el-form-item label="规则名">
          <el-input v-model="ruleForm.name" :maxlength="128" />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="ruleForm.kind">
            <el-radio value="keyword">关键字</el-radio>
            <el-radio value="count">数量阈值</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="ruleForm.kind === 'keyword'" label="关键字">
          <el-input v-model="keywordInput" placeholder="多个关键字用英文逗号分隔" />
        </el-form-item>
        <el-form-item v-else label="数量">
          <el-input-number v-model="countThreshold" :min="1" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="ruleEnabled" active-value="1" inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ruleVisible = false">取消</el-button>
        <el-button type="primary" :loading="ruleSaving" @click="onSaveRule">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import axios from 'axios'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  approveApproval,
  cancelApproval,
  createRule,
  deleteRule,
  getApproval,
  listApprovals,
  listRules,
  rejectApproval,
  updateRule,
} from '../../api/approval'
import type { ApprovalDetail, ApprovalOut, ApprovalQuery, RuleOut } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const rulesLoading = ref(false)
const rows = ref<ApprovalOut[]>([])
const rules = ref<RuleOut[]>([])
const total = ref(0)
const scope = ref<'all' | 'me' | 'todo'>('all')

const query = reactive<ApprovalQuery>({ page: 1, size: 10 })

const statusOptions = [
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已拒绝' },
  { value: 'canceled', label: '已撤销' },
]

function statusLabel(s: string): string {
  return statusOptions.find((o) => o.value === s)?.label ?? s
}

function statusTag(s: string): string {
  switch (s) {
    case 'pending':
      return 'warning'
    case 'approved':
      return 'success'
    case 'rejected':
      return 'danger'
    case 'canceled':
      return 'info'
    default:
      return 'info'
  }
}

function bizTypeLabel(t: string): string {
  return t === 'terminal' ? '终端会话' : '命令执行'
}

function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

function timelineType(action: string): string {
  return action === 'approve' ? 'success' : action === 'reject' ? 'danger' : action === 'cancel' ? 'info' : 'primary'
}

function timelineAction(action: string): string {
  switch (action) {
    case 'approve':
      return '通过'
    case 'reject':
      return '拒绝'
    case 'cancel':
      return '撤销'
    case 'create':
      return '发起申请'
    default:
      return action
  }
}

async function load() {
  loading.value = true
  try {
    const params: ApprovalQuery = { ...query }
    if (scope.value === 'me') params.mine = true
    else if (scope.value === 'todo') params.todo = true
    const page = await listApprovals(params)
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.status = undefined
  query.biz_type = undefined
  query.page = 1
  load()
}

function onScopeChange() {
  query.page = 1
  load()
}

async function loadRules() {
  rulesLoading.value = true
  try {
    rules.value = await listRules()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    rulesLoading.value = false
  }
}

const detailVisible = ref(false)
const detail = ref<ApprovalDetail | null>(null)

async function openDetail(id: number) {
  try {
    detail.value = await getApproval(id)
    detailVisible.value = true
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const decideVisible = ref(false)
const decideLoading = ref(false)
const decideForm = reactive({ comment: '' })
const decideId = ref<number | null>(null)
const decideAction = ref<'approve' | 'reject' | 'cancel'>('approve')
const decideTitle = ref('')

function openDecide(row: ApprovalOut, action: 'approve' | 'reject' | 'cancel') {
  decideId.value = row.id
  decideAction.value = action
  decideForm.comment = ''
  decideTitle.value = action === 'approve' ? '通过审批' : action === 'reject' ? '拒绝审批' : '撤销申请'
  decideVisible.value = true
}

async function onDecide() {
  if (decideId.value == null) return
  decideLoading.value = true
  try {
    const payload = { comment: decideForm.comment }
    if (decideAction.value === 'approve') await approveApproval(decideId.value, payload)
    else if (decideAction.value === 'reject') await rejectApproval(decideId.value, payload)
    else await cancelApproval(decideId.value)
    ElMessage.success('操作成功')
    decideVisible.value = false
    load()
  } catch (e) {
    const conflict = axios.isAxiosError(e) && e.response?.status === 409
    ElMessage.error(extractError(e) + (conflict ? '（refresh and retry，请刷新后重试）' : ''))
  } finally {
    decideLoading.value = false
  }
}

const ruleVisible = ref(false)
const ruleSaving = ref(false)
const ruleId = ref<number | null>(null)
const ruleForm = reactive({ name: '', kind: 'keyword' })
const keywordInput = ref('')
const countThreshold = ref(50)
const ruleEnabled = ref('1')

function openRule(row?: RuleOut) {
  if (row) {
    ruleId.value = row.id
    ruleForm.name = row.name
    ruleForm.kind = row.kind
    ruleEnabled.value = String(row.enabled)
    const v = row.value as Record<string, unknown>
    if (row.kind === 'keyword') {
      const kws = Array.isArray(v.keywords) ? (v.keywords as string[]).join(',') : ''
      keywordInput.value = kws
    } else {
      countThreshold.value = (v.count as number) ?? 50
    }
  } else {
    ruleId.value = null
    ruleForm.name = ''
    ruleForm.kind = 'keyword'
    keywordInput.value = ''
    countThreshold.value = 50
    ruleEnabled.value = '1'
  }
  ruleVisible.value = true
}

async function onSaveRule() {
  if (ruleForm.name.length < 1) {
    ElMessage.warning('请输入规则名')
    return
  }
  const value: Record<string, unknown> =
    ruleForm.kind === 'keyword'
      ? { keywords: keywordInput.value.split(',').map((s) => s.trim()).filter(Boolean) }
      : { count: countThreshold.value }
  ruleSaving.value = true
  try {
    const payload = { name: ruleForm.name, kind: ruleForm.kind, value, enabled: Number(ruleEnabled.value) }
    if (ruleId.value) await updateRule(ruleId.value, payload)
    else await createRule(payload)
    ElMessage.success('保存成功')
    ruleVisible.value = false
    loadRules()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    ruleSaving.value = false
  }
}

async function onDeleteRule(row: RuleOut) {
  try {
    await ElMessageBox.confirm(`确定删除规则「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteRule(row.id)
    ElMessage.success('已删除')
    loadRules()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => {
  load()
  loadRules()
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
.card-gap {
  margin-top: 16px;
}
</style>
