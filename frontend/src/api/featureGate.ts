import axios from 'axios'
import type { Result } from './types'

/**
 * A2 feature-off detection (acceptance checklist §G2).
 * Exact predicate: HTTP 400 && body.code === 400 && body.message === "feature disabled".
 * 403 (`forbidden` / `permission denied`) is a real permission denial and MUST NOT be
 * treated as "未启用" (§G2b).
 */
export function isFeatureDisabled(error: unknown): boolean {
  if (!axios.isAxiosError(error)) return false
  const resp = error.response
  if (!resp || resp.status !== 400) return false
  const body = resp.data as Result<unknown> | undefined
  return body?.code === 400 && body?.message === 'feature disabled'
}
