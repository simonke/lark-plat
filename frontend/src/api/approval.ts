/**
 * Approval API — new file frontend/src/api/approval.ts (stage 4)
 * Contract: api-design v2.1 §9 (/approvals), shapes @ backend schemas.
 * Approve/reject are guarded by an optimistic-lock version; server returns 409 on
 * version conflict, the UI surfaces a refresh prompt.
 */
import http from './http'
import type {
  Page,
  ApprovalOut,
  ApprovalDetail,
  ApprovalQuery,
  ApproveIn,
  RuleIn,
  RuleOut,
} from './types'

export async function listApprovals(params?: ApprovalQuery): Promise<Page<ApprovalOut>> {
  const { data } = await http.get<import('./types').Result<Page<ApprovalOut>>>('/approvals', { params })
  return data.data
}

export async function getApproval(id: number): Promise<ApprovalDetail> {
  const { data } = await http.get<import('./types').Result<ApprovalDetail>>(`/approvals/${id}`)
  return data.data
}

export async function approveApproval(id: number, payload: ApproveIn): Promise<void> {
  await http.post<import('./types').Result<void>>(`/approvals/${id}/approve`, payload)
}

export async function rejectApproval(id: number, payload: ApproveIn): Promise<void> {
  await http.post<import('./types').Result<void>>(`/approvals/${id}/reject`, payload)
}

export async function cancelApproval(id: number): Promise<void> {
  await http.post<import('./types').Result<void>>(`/approvals/${id}/cancel`)
}

export async function listRules(): Promise<RuleOut[]> {
  const { data } = await http.get<import('./types').Result<RuleOut[]>>('/approvals/rules')
  return data.data
}

export async function createRule(payload: RuleIn): Promise<RuleOut> {
  const { data } = await http.post<import('./types').Result<RuleOut>>('/approvals/rules', payload)
  return data.data
}

export async function updateRule(ruleId: number, payload: RuleIn): Promise<void> {
  await http.put<import('./types').Result<void>>(`/approvals/rules/${ruleId}`, payload)
}

export async function deleteRule(ruleId: number): Promise<void> {
  await http.delete<import('./types').Result<void>>(`/approvals/rules/${ruleId}`)
}
