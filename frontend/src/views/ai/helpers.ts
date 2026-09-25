/**
 * P4 AIOps display helpers — frontend/src/views/ai/helpers.ts
 * Pure functions (unit-testable without mounting). Mirrors the frozen constants
 * OPS_EVENT_SOURCES / AI_ACTION_DECISIONS from backend/app/db/models.
 */
import type { OpsEventSource, AiActionDecision } from '../../api/types'

export const OPS_EVENT_SOURCES: readonly OpsEventSource[] = ['monitor', 'exec', 'audit', 'ticket', 'kb']
export const AI_ACTION_DECISIONS: readonly AiActionDecision[] = ['adopted', 'rejected', 'auto']

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
