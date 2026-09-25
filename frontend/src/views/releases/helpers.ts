import type { ReleaseEnv, ReleaseStatus } from '../../api/types'

export type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'

export const ENV_OPTIONS: { value: ReleaseEnv; label: string }[] = [
  { value: 'dev', label: '开发' },
  { value: 'test', label: '测试' },
  { value: 'prod', label: '生产' },
]

export const RELEASE_STATUS_OPTIONS: { value: ReleaseStatus; label: string }[] = [
  { value: 'pending', label: '待发布' },
  { value: 'deploying', label: '发布中' },
  { value: 'canary', label: '灰度中' },
  { value: 'succeeded', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'rolled_back', label: '已回滚' },
  { value: 'cancelled', label: '已取消' },
]

export function envLabel(v: string): string {
  return ENV_OPTIONS.find((o) => o.value === v)?.label ?? v
}

export function releaseStatusLabel(v: string): string {
  return RELEASE_STATUS_OPTIONS.find((o) => o.value === v)?.label ?? v
}

export function releaseStatusTag(v: string): TagType {
  switch (v) {
    case 'succeeded':
      return 'success'
    case 'failed':
      return 'danger'
    case 'rolled_back':
      return 'warning'
    case 'cancelled':
      return 'info'
    case 'deploying':
    case 'canary':
      return 'primary'
    default:
      return 'warning'
  }
}

/**
 * §14.1 / @架构 seq3077 + P3-6 tuple v1 (seq3127): action -> allowed_from (illegal source -> 409).
 * deploy   <- pending
 * canary   <- pending|deploying
 * fail     <- deploying|canary
 * promote  <- canary
 * rollback <- deploying|canary|failed
 * cancel   <- pending|deploying|canary
 */
export function canCancel(v: string): boolean {
  return v === 'pending' || v === 'deploying' || v === 'canary'
}

export function isTerminal(v: string): boolean {
  return v === 'succeeded' || v === 'failed' || v === 'rolled_back' || v === 'cancelled'
}

export function canCanary(v: string): boolean {
  return v === 'pending' || v === 'deploying'
}

export function canDeploy(v: string): boolean {
  return v === 'pending'
}

export function canFail(v: string): boolean {
  return v === 'deploying' || v === 'canary'
}

export function canPromote(v: string): boolean {
  return v === 'canary'
}

export function canRollback(v: string): boolean {
  return v === 'deploying' || v === 'canary' || v === 'failed'
}

export function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}
