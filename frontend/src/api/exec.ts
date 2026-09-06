/**
 * Exec API — new file frontend/src/api/exec.ts (stage 3 batch 1)
 * Contract: api-design v2.1 §5 (/exec/tasks), shapes @ backend schemas e04d85e.
 * Realtime log WS: GET ws-token -> WS /ws/exec/{task_host_id}?token= (5min JWT bound
 * to task_host_id; close 4401=token, 4404=not found). REST remains the replay source
 * via after_seq cursor; stop is REST-only.
 */
import http from './http'
import type {
  Result,
  Page,
  ExecTaskOut,
  ExecTaskDetail,
  ExecTaskCreate,
  ExecTaskQuery,
  ExecStats,
  ExecLogPage,
  WsTokenOut,
} from './types'

export async function getTasks(params?: ExecTaskQuery): Promise<Page<ExecTaskOut>> {
  const { data } = await http.get<Result<Page<ExecTaskOut>>>('/exec/tasks', { params })
  return data.data
}

export async function createTask(payload: ExecTaskCreate): Promise<ExecTaskDetail> {
  const { data } = await http.post<Result<ExecTaskDetail>>('/exec/tasks', payload)
  return data.data
}

export async function getTask(taskId: number): Promise<ExecTaskDetail> {
  const { data } = await http.get<Result<ExecTaskDetail>>(`/exec/tasks/${taskId}`)
  return data.data
}

export async function getTaskStats(taskId: number): Promise<ExecStats> {
  const { data } = await http.get<Result<ExecStats>>(`/exec/tasks/${taskId}/stats`)
  return data.data
}

export async function stopTask(taskId: number): Promise<void> {
  await http.post<Result<void>>(`/exec/tasks/${taskId}/stop`)
}

export async function retryTask(taskId: number): Promise<void> {
  await http.post<Result<void>>(`/exec/tasks/${taskId}/retry`)
}

export async function getLogs(
  taskId: number,
  taskHostId: number,
  afterSeq = 0,
  size = 200,
): Promise<ExecLogPage> {
  const { data } = await http.get<Result<ExecLogPage>>(
    `/exec/tasks/${taskId}/hosts/${taskHostId}/logs`,
    { params: { after_seq: afterSeq, size } },
  )
  return data.data
}

export async function getWsToken(taskId: number, taskHostId: number): Promise<string> {
  const { data } = await http.get<Result<WsTokenOut>>(
    `/exec/tasks/${taskId}/hosts/${taskHostId}/ws-token`,
  )
  return data.data.token
}
