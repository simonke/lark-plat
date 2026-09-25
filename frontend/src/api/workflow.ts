import http from './http'
import type {
  Result,
  Page,
  Workflow,
  WorkflowOut,
  WorkflowCreate,
  WorkflowUpdate,
  WorkflowVersion,
  WorkflowVersionList,
  WorkflowVersionCreate,
  WorkflowRun,
  WorkflowRunDetail,
  WorkflowRunIn,
  WorkflowRunId,
  WsTokenOut,
} from './types'

export async function listWorkflows(params?: {
  name?: string
  enabled?: number
  page?: number
  size?: number
}): Promise<Page<Workflow>> {
  const { data } = await http.get<Result<Page<Workflow>>>('/workflows', { params })
  return data.data
}

export async function createWorkflow(payload: WorkflowCreate): Promise<WorkflowOut> {
  const { data } = await http.post<Result<WorkflowOut>>('/workflows', payload)
  return data.data
}

export async function getWorkflow(id: number): Promise<WorkflowOut> {
  const { data } = await http.get<Result<WorkflowOut>>(`/workflows/${id}`)
  return data.data
}

export async function updateWorkflow(id: number, payload: WorkflowUpdate): Promise<WorkflowOut> {
  const { data } = await http.put<Result<WorkflowOut>>(`/workflows/${id}`, payload)
  return data.data
}

export async function deleteWorkflow(id: number): Promise<void> {
  await http.delete<Result<void>>(`/workflows/${id}`)
}

export async function listWorkflowVersions(id: number): Promise<WorkflowVersionList> {
  const { data } = await http.get<Result<WorkflowVersionList>>(`/workflows/${id}/versions`)
  return data.data
}

export async function createWorkflowVersion(
  id: number,
  payload: WorkflowVersionCreate,
): Promise<WorkflowVersion> {
  const { data } = await http.post<Result<WorkflowVersion>>(`/workflows/${id}/versions`, payload)
  return data.data
}

export async function rollbackWorkflow(id: number, version: number): Promise<WorkflowOut> {
  const { data } = await http.post<Result<WorkflowOut>>(`/workflows/${id}/rollback`, { version })
  return data.data
}

export async function runWorkflow(
  id: number,
  payload?: WorkflowRunIn,
  idempotencyKey?: string,
): Promise<WorkflowRunId> {
  const headers: Record<string, string> = {}
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey
  const { data } = await http.post<Result<WorkflowRunId>>(
    `/workflows/${id}/run`,
    payload ?? {},
    { headers },
  )
  return data.data
}

export async function listWorkflowRuns(params?: {
  workflow_id?: number
  status?: string
  page?: number
  size?: number
}): Promise<Page<WorkflowRun>> {
  const { data } = await http.get<Result<Page<WorkflowRun>>>('/workflow-runs', { params })
  return data.data
}

export async function getWorkflowRun(id: number): Promise<WorkflowRunDetail> {
  const { data } = await http.get<Result<WorkflowRunDetail>>(`/workflow-runs/${id}`)
  return data.data
}

export async function getWorkflowRunWsToken(id: number): Promise<string> {
  const { data } = await http.get<Result<WsTokenOut>>(`/workflow-runs/${id}/ws-token`)
  return data.data.token
}

export async function cancelWorkflowRun(id: number): Promise<WorkflowRun> {
  const { data } = await http.post<Result<WorkflowRun>>(`/workflow-runs/${id}/cancel`)
  return data.data
}

export async function retryWorkflowRun(id: number): Promise<WorkflowRunId> {
  const { data } = await http.post<Result<WorkflowRunId>>(`/workflow-runs/${id}/retry`)
  return data.data
}
