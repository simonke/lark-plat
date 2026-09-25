import type { CicdProviderType } from '../../api/types'

export const PROVIDER_TYPE_OPTIONS: { value: CicdProviderType; label: string }[] = [
  { value: 'gitlab', label: 'GitLab' },
  { value: 'jenkins', label: 'Jenkins' },
  { value: 'generic', label: '通用 Webhook' },
]

export function providerTypeLabel(v: string): string {
  return PROVIDER_TYPE_OPTIONS.find((o) => o.value === v)?.label ?? v
}

export function providerStatusTag(v: string): 'success' | 'warning' | 'info' | 'danger' {
  switch (v) {
    case 'ok':
    case 'online':
      return 'success'
    case 'offline':
    case 'error':
      return 'danger'
    case 'unknown':
      return 'info'
    default:
      return 'info'
  }
}

export function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}
