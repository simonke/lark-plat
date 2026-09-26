/**
 * P4 AIOps display helpers — frontend/src/views/ai/helpers.ts
 * Pure functions (unit-testable without mounting). Mirrors the frozen constants
 * OPS_EVENT_SOURCES / AI_ACTION_DECISIONS from backend/app/db/models.
 */
import type { OpsEventSource, AiActionDecision } from '../../api/types'

export const OPS_EVENT_SOURCES: readonly OpsEventSource[] = ['monitor', 'exec', 'audit', 'ticket', 'kb']
// P6 add-only: mirrors the backend `AI_ACTION_DECISIONS` (+ "dry_run").
export const AI_ACTION_DECISIONS: readonly AiActionDecision[] = ['adopted', 'rejected', 'auto', 'dry_run']

const SOURCE_LABELS: Record<string, string> = {
  monitor: '监控',
  exec: '执行',
  audit: '审计',
  ticket: '工单',
  kb: '知识库',
}

const DECISION_LABELS: Record<string, string> = {
  adopted: '已采纳',
  rejected: '已否决',
  auto: '自动记录',
  dry_run: '预演',
}

const BRANCH_LABELS: Record<string, string> = {
  vector: '向量',
  fts: '全文',
  hybrid: '混合',
}

export function sourceLabel(v: string): string {
  return SOURCE_LABELS[v] ?? v
}

export function sourceTag(v: string): string {
  switch (v) {
    case 'monitor':
      return 'danger'
    case 'exec':
      return 'warning'
    case 'audit':
      return 'info'
    case 'ticket':
      return 'primary'
    case 'kb':
      return 'success'
    default:
      return ''
  }
}

export function decisionLabel(v: string): string {
  return DECISION_LABELS[v] ?? v
}

export function decisionTag(v: string): string {
  switch (v) {
    case 'adopted':
      return 'success'
    case 'rejected':
      return 'danger'
    default:
      return 'info'
  }
}

export function branchLabel(v: string): string {
  return BRANCH_LABELS[v] ?? v
}

export function confidencePercent(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return `${Math.round(v * 100)}%`
}

export function eventSummary(e: { entity_type: string; entity_id: string; action: string }): string {
  return `${e.entity_type}#${e.entity_id} · ${e.action}`
}

export function shortTrace(t: string | null | undefined): string {
  if (!t) return '-'
  return t.length > 24 ? `${t.slice(0, 21)}…` : t
}

export function articleIdFromDocRef(docRef: string | null | undefined): number | null {
  if (docRef === null || docRef === undefined || docRef === '') return null
  const id = Number(docRef)
  return Number.isInteger(id) && id > 0 ? id : null
}

// ---------------------------------------------------------------- P5 E4/E5 helpers

/** E4 depth domain mirrors cmdb_service._clamp_depth: 0..3, default 2, 0 legal. */
export const RCA_DEPTH_MIN = 0
export const RCA_DEPTH_MAX = 3
export const RCA_DEPTH_DEFAULT = 2

/** E5 reuses the P3-4 workflow engine; `kind` discriminates, no second executor. */
export const PLAYBOOK_KINDS: readonly string[] = ['workflow', 'playbook']

/** Coerce any inbound/UI depth to a legal `0..3` value, falling back to default 2. */
export function normalizeRcaDepth(value: number | null | undefined): number {
  if (value === null || value === undefined) return RCA_DEPTH_DEFAULT
  const n = Number(value)
  if (!Number.isInteger(n) || n < RCA_DEPTH_MIN || n > RCA_DEPTH_MAX) return RCA_DEPTH_DEFAULT
  return n
}

const SEVERITY_LABELS: Record<string, string> = {
  critical: '严重',
  warning: '警告',
  info: '信息',
}

export function severityLabel(v: string | null | undefined): string {
  if (!v) return '-'
  return SEVERITY_LABELS[v] ?? v
}

export function severityTag(v: string | null | undefined): string {
  switch (v) {
    case 'critical':
      return 'danger'
    case 'warning':
      return 'warning'
    case 'info':
      return 'info'
    default:
      return 'info'
  }
}

export function rootEntityLabel(root: { type?: string; id?: string | number | null; name?: string | null } | null | undefined): string {
  if (!root) return '-'
  const label = root.name || root.id
  return label === null || label === undefined || label === '' ? '-' : `${root.type ?? '?'}#${label}`
}

// ---------------------------------------------------------------- P6 E6 (AIOps L4) helpers

/** L0..L4 ladder (display order); the matrix VALUES come from the backend. */
export const AUTOMATION_LEVELS: readonly string[] = ['L0', 'L1', 'L2', 'L3', 'L4']

/** Highest tier enabled this phase (L5 self-healing is an explicit non-goal). */
export const AUTOMATION_MAX_LEVEL = 'L4'
/** Default tier until L4 is explicitly switched on (server default L3). */
export const AUTOMATION_DEFAULT_LEVEL = 'L3'

/** Mirror of the backend risk vocabulary (lowercase, single source). */
export const RISK_LEVELS: readonly string[] = ['low', 'medium', 'high']
/** Mirror of the services-layer leaf constant `APPROVAL_MODES`. */
export const APPROVAL_MODES: readonly string[] = ['auto_policy', 'manual']
/** L4 auto set: only `low` may auto-remediate (backend `L4_AUTO_RISK_LEVELS`). */
export const L4_AUTO_RISK_LEVELS: readonly string[] = ['low']

const RISK_LABELS: Record<string, string> = { low: '低', medium: '中', high: '高' }
const APPROVAL_MODE_LABELS: Record<string, string> = { auto_policy: '策略自动批准', manual: '人工审批' }
const CIRCUIT_STATE_LABELS: Record<string, string> = { closed: '正常', half: '半开', open: '熔断' }

export function riskLabel(v: string | null | undefined): string {
  if (!v) return '-'
  return RISK_LABELS[v] ?? v
}

export function riskTag(v: string | null | undefined): string {
  switch (v) {
    case 'low':
      return 'success'
    case 'medium':
      return 'warning'
    case 'high':
      return 'danger'
    default:
      return 'info'
  }
}

/** Only `low` may run on L4 (`risk_level in L4_AUTO_RISK_LEVELS`). */
export function isAutoEligibleRisk(v: string | null | undefined): boolean {
  return v !== null && v !== undefined && L4_AUTO_RISK_LEVELS.includes(v)
}

export function approvalModeLabel(v: string | null | undefined): string {
  if (!v) return '-'
  return APPROVAL_MODE_LABELS[v] ?? v
}

export function approvalModeTag(v: string | null | undefined): string {
  switch (v) {
    case 'auto_policy':
      return 'warning'
    case 'manual':
      return 'info'
    default:
      return 'info'
  }
}

export function circuitStateLabel(v: string | null | undefined): string {
  if (!v) return '-'
  return CIRCUIT_STATE_LABELS[v] ?? v
}

export function circuitStateTag(v: string | null | undefined): string {
  switch (v) {
    case 'closed':
      return 'success'
    case 'half':
      return 'warning'
    case 'open':
      return 'danger'
    default:
      return 'info'
  }
}

/** Map a tier code (e.g. "L4") to its ladder index, or -1 when unknown. */
export function levelIndex(v: string | null | undefined): number {
  if (!v) return -1
  return AUTOMATION_LEVELS.indexOf(v)
}

/** True when `level` is at or below `max` on the L0..L4 ladder (fail-closed otherwise). */
export function isLevelWithin(level: string | null | undefined, max: string = AUTOMATION_MAX_LEVEL): boolean {
  const a = levelIndex(level)
  const b = levelIndex(max)
  return a >= 0 && b >= 0 && a <= b
}

/** Deterministic dry-run idempotency key (same inputs -> same key; dedupe seam). */
export function buildDryRunKey(action: string | null | undefined, now: number = Date.now()): string {
  return `dry-${(action || 'noop').trim() || 'noop'}-${now}`
}
