/**
 * Transfer API — new file frontend/src/api/transfer.ts (P2-1)
 * Contract: api-design-v3.md §1 (/transfer), frozen design.
 * Realtime progress: GET ws-token -> WS /ws/transfer/{transfer_host_id}?token=
 * (5min JWT bound to transfer_host_id); REST logs remain replay source via
 * after_seq cursor; stop/retry are REST-only (mirrors exec module).
 */
import http from './http'
import type {
  Result,
  Page,
  TransferUploadResult,
  TransferPackageOut,
  TransferPackageDetail,
  TransferPackageQuery,
  TransferTaskCreate,
  TransferTaskCreated,
  TransferTaskOut,
  TransferTaskMineOut,
  TransferTaskDetail,
  TransferTaskQuery,
  TransferLogPage,
  TransferStats,
  WsTokenOut,
} from './types'

export async function uploadPackage(files: File[], name?: string): Promise<TransferUploadResult> {
  const formData = new FormData()
  if (name) formData.append('name', name)
  for (const f of files) formData.append('files', f)
  const { data } = await http.post<Result<TransferUploadResult>>('/transfer/packages', formData)
  return data.data
}

export async function deletePackage(id: number): Promise<void> {
  await http.delete<Result<void>>(`/transfer/packages/${id}`)
}

export async function getPackage(id: number): Promise<TransferPackageDetail> {
  const { data } = await http.get<Result<TransferPackageDetail>>(`/transfer/packages/${id}`)
  return data.data
}

export async function getPackages(params?: TransferPackageQuery): Promise<Page<TransferPackageOut>> {
  const { data } = await http.get<Result<Page<TransferPackageOut>>>('/transfer/packages', { params })
  return data.data
}

export async function createTransferTask(
  payload: TransferTaskCreate,
): Promise<TransferTaskCreated> {
  const { data } = await http.post<Result<TransferTaskCreated>>('/transfer/tasks', payload)
  return data.data
}

export async function getTransferTasks(params?: TransferTaskQuery): Promise<Page<TransferTaskOut>> {
  const { data } = await http.get<Result<Page<TransferTaskOut>>>('/transfer/tasks', { params })
  return data.data
}

export async function getMyTransferTasks(params?: TransferTaskQuery): Promise<Page<TransferTaskMineOut>> {
  const { data } = await http.get<Result<Page<TransferTaskMineOut>>>('/transfer/tasks/mine', { params })
  return data.data
}

export async function getTransferTask(id: number): Promise<TransferTaskDetail> {
  const { data } = await http.get<Result<TransferTaskDetail>>(`/transfer/tasks/${id}`)
  return data.data
}

export async function getTransferStats(id: number): Promise<TransferStats> {
  const { data } = await http.get<Result<TransferStats>>(`/transfer/tasks/${id}/stats`)
  return data.data
}

export async function stopTransferTask(id: number): Promise<void> {
  await http.post<Result<void>>(`/transfer/tasks/${id}/stop`)
}

export async function retryTransferHost(taskId: number, transferHostId: number): Promise<void> {
  await http.post<Result<void>>(`/transfer/tasks/${taskId}/hosts/${transferHostId}/retry`)
}

export async function getTransferLogs(
  taskId: number,
  transferHostId: number,
  afterSeq = 0,
  size = 200,
): Promise<TransferLogPage> {
  const { data } = await http.get<Result<TransferLogPage>>(
    `/transfer/tasks/${taskId}/hosts/${transferHostId}/logs`,
    { params: { after_seq: afterSeq, size } },
  )
  return data.data
}

export async function getTransferWsToken(taskId: number, transferHostId: number): Promise<string> {
  const { data } = await http.get<Result<WsTokenOut>>(
    `/transfer/tasks/${taskId}/hosts/${transferHostId}/ws-token`,
  )
  return data.data.token
}