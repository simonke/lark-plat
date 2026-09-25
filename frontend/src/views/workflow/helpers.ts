import type { WorkflowDefinition, WorkflowNodeType, WorkflowRunStatus, WorkflowTriggerType } from '../../api/types'

export type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

export const NODE_TYPE_OPTIONS: { value: WorkflowNodeType; label: string }[] = [
  { value: 'exec_task', label: '执行任务' },
  { value: 'manual_approval', label: '人工审批' },
  { value: 'wait', label: '等待' },
  { value: 'callback', label: '回调' },
  { value: 'sleep', label: '延时' },
]

export const RUN_STATUS_OPTIONS: { value: WorkflowRunStatus; label: string }[] = [
  { value: 'pending', label: '待运行' },
  { value: 'running', label: '运行中' },
  { value: 'succeeded', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

export const TRIGGER_TYPE_OPTIONS: { value: WorkflowTriggerType; label: string }[] = [
  { value: 'manual', label: '手动' },
  { value: 'ticket', label: '工单' },
  { value: 'schedule', label: '定时' },
  { value: 'alert', label: '告警' },
  { value: 'release', label: '发布' },
]

export function nodeTypeLabel(v: string): string {
  return NODE_TYPE_OPTIONS.find((o) => o.value === v)?.label ?? v
}

export function runStatusLabel(v: string): string {
  return RUN_STATUS_OPTIONS.find((o) => o.value === v)?.label ?? v
}

export function runStatusTag(v: string): TagType {
  switch (v) {
    case 'succeeded':
      return 'success'
    case 'failed':
      return 'danger'
    case 'cancelled':
      return 'info'
    case 'running':
      return 'primary'
    default:
      return 'warning'
  }
}

export function nodeStatusLabel(v: string): string {
  const map: Record<string, string> = {
    pending: '待运行',
    running: '运行中',
    succeeded: '成功',
    failed: '失败',
    skipped: '已跳过',
    waiting: '等待中',
  }
  return map[v] ?? v
}

export function nodeStatusTag(v: string): TagType {
  switch (v) {
    case 'succeeded':
      return 'success'
    case 'failed':
      return 'danger'
    case 'skipped':
      return 'info'
    case 'running':
      return 'primary'
    case 'waiting':
      return 'warning'
    default:
      return 'info'
  }
}

export function triggerLabel(v: string): string {
  return TRIGGER_TYPE_OPTIONS.find((o) => o.value === v)?.label ?? v
}

export function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

export function formatDefinition(def: WorkflowDefinition | null | undefined): string {
  return JSON.stringify(def ?? { nodes: [] }, null, 2)
}

export interface CallbackOutput {
  token?: string
  url?: string
  expires_at?: string
}

/** node.output.callback = {token,url,expires_at} for a `waiting` callback node (engine tuple §K). */
export function callbackOutput(
  output: Record<string, unknown> | null | undefined,
): CallbackOutput | null {
  const cb = output?.callback
  if (cb && typeof cb === 'object') return cb as CallbackOutput
  return null
}

export function parseDefinition(text: string): WorkflowDefinition {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('定义不是合法 JSON')
  }
  if (!parsed || typeof parsed !== 'object' || !Array.isArray((parsed as { nodes?: unknown }).nodes)) {
    throw new Error('定义必须形如 {"nodes":[...]}')
  }
  return parsed as WorkflowDefinition
}
