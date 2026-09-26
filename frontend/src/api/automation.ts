/**
 * P6 (E6) governed auto-remediation API — frontend/src/api/automation.ts
 * Contract: @架构 P6 tuple r1 (msg e2066572 + notes r1.1-r1.7) + @需求 §30 v0.1.6.
 * Backend: app/api/v1/endpoints/ai_automation.py + ai_automation_service.py (5417f75).
 *
 * Routes are ALWAYS registered ((A)); the feature flag `ai.auto_remediate` is enforced
 * feature-first server-side, so with it off ANY caller gets 400/403 (never 404) — callers
 * should render an "未启用" empty state on error. Gates: reads `ai:use`, writes `ai:admin`.
 *
 * `auto_policy` remediation stays on the existing exec+approval primitive: never expose a
 * bypass-approval write entry from the FE.
 */
import http from './http'
import type {
  Result,
  AutomationLevel,
  AutomationWhitelistPage,
  AutomationWhitelistQuery,
  AutomationWhitelistCreate,
  AutomationWhitelistUpdate,
  AutomationWhitelistItem,
  DryRunIn,
  DryRunResult,
  AutomationRollbackResult,
  CircuitBreakerState,
} from './types'

/** FR-E6-1: read the governed level matrix + current tier (ai:use). */
export async function getAutomationLevel(): Promise<AutomationLevel> {
  const { data } = await http.get<Result<AutomationLevel>>('/ai/automation/level')
  return data.data
}

/** FR-E6-1: switch the current tier (ai:admin; idempotent; audited server-side). */
export async function setAutomationLevel(current: string): Promise<AutomationLevel> {
  const { data } = await http.put<Result<AutomationLevel>>('/ai/automation/level', { current })
  return data.data
}

/** FR-E6-2: paginated whitelist (ai:admin). */
export async function listAutomationWhitelist(
  params?: AutomationWhitelistQuery,
): Promise<AutomationWhitelistPage> {
  const { data } = await http.get<Result<AutomationWhitelistPage>>('/ai/automation/whitelist', { params })
  return data.data
}

/** FR-E6-2: create a whitelist entry (ai:admin). */
export async function createAutomationWhitelist(
  payload: AutomationWhitelistCreate,
): Promise<AutomationWhitelistItem> {
  const { data } = await http.post<Result<AutomationWhitelistItem>>('/ai/automation/whitelist', payload)
  return data.data
}

/** FR-E6-2: update a whitelist entry (ai:admin). */
export async function updateAutomationWhitelist(
  itemId: number,
  payload: AutomationWhitelistUpdate,
): Promise<AutomationWhitelistItem> {
  const { data } = await http.put<Result<AutomationWhitelistItem>>(
    `/ai/automation/whitelist/${itemId}`,
    payload,
  )
  return data.data
}

/** FR-E6-2: delete a whitelist entry (ai:admin). */
export async function deleteAutomationWhitelist(itemId: number): Promise<{ id: number; deleted: boolean }> {
  const { data } = await http.delete<Result<{ id: number; deleted: boolean }>>(
    `/ai/automation/whitelist/${itemId}`,
  )
  return data.data
}

/** FR-E6-7: read-only dry-run preview (ai:use); one `dry_run` audit row is recorded. */
export async function automationDryRun(payload: DryRunIn): Promise<DryRunResult> {
  const { data } = await http.post<Result<DryRunResult>>('/ai/automation/dry-run', payload)
  return data.data
}

/** FR-E6-4: roll a remediation run back (ai:admin; idempotent; via exec+approval). */
export async function rollbackAutomationRun(runId: number): Promise<AutomationRollbackResult> {
  const { data } = await http.post<Result<AutomationRollbackResult>>(
    `/ai/automation/runs/${runId}/rollback`,
    {},
  )
  return data.data
}

/** FR-E6-4: circuit-breaker status (ai:use). */
export async function getCircuitBreaker(): Promise<CircuitBreakerState> {
  const { data } = await http.get<Result<CircuitBreakerState>>('/ai/automation/circuit-breaker')
  return data.data
}
