import http from './http'
import type {
  Result,
  Page,
  ScheduleOut,
  ScheduleCreate,
  ScheduleUpdate,
  ScheduleQuery,
  ScheduleRunOut,
  ScheduleRunNowResult,
  ScheduleRetryResult,
} from './types'

export async function listSchedules(params?: ScheduleQuery): Promise<Page<ScheduleOut>> {
  const { data } = await http.get<Result<Page<ScheduleOut>>>('/schedules', { params })
  return data.data
}

export async function createSchedule(payload: ScheduleCreate): Promise<{ id: number }> {
  const { data } = await http.post<Result<{ id: number }>>('/schedules', payload)
  return data.data
}

export async function updateSchedule(id: number, payload: ScheduleUpdate): Promise<void> {
  await http.put<Result<void>>(`/schedules/${id}`, payload)
}

export async function deleteSchedule(id: number): Promise<void> {
  await http.delete<Result<void>>(`/schedules/${id}`)
}

export async function setScheduleStatus(id: number, enabled: number): Promise<void> {
  await http.put<Result<void>>(`/schedules/${id}/status`, { enabled })
}

export async function runNow(id: number): Promise<ScheduleRunNowResult> {
  const { data } = await http.post<Result<ScheduleRunNowResult>>(`/schedules/${id}/run-now`)
  return data.data
}

export async function listScheduleRuns(
  id: number,
  params?: { page?: number; size?: number },
): Promise<Page<ScheduleRunOut>> {
  const { data } = await http.get<Result<Page<ScheduleRunOut>>>(`/schedules/${id}/runs`, { params })
  return data.data
}

export async function retryScheduleRun(id: number, runId: number): Promise<ScheduleRetryResult> {
  const { data } = await http.post<Result<ScheduleRetryResult>>(`/schedules/${id}/runs/${runId}/retry`)
  return data.data
}