import http from './http'
import type {
  Result,
  Page,
  CicdProviderOut,
  CicdProviderCreate,
  CicdProviderUpdate,
  CicdProviderTestResult,
  CicdProviderQuery,
} from './types'

export async function listCicdProviders(params?: CicdProviderQuery): Promise<Page<CicdProviderOut>> {
  const { data } = await http.get<Result<Page<CicdProviderOut>>>('/cicd/providers', { params })
  return data.data
}

export async function createCicdProvider(payload: CicdProviderCreate): Promise<CicdProviderOut> {
  const { data } = await http.post<Result<CicdProviderOut>>('/cicd/providers', payload)
  return data.data
}

export async function updateCicdProvider(
  id: number,
  payload: CicdProviderUpdate,
): Promise<CicdProviderOut> {
  const { data } = await http.put<Result<CicdProviderOut>>(`/cicd/providers/${id}`, payload)
  return data.data
}

export async function deleteCicdProvider(id: number): Promise<void> {
  await http.delete<Result<void>>(`/cicd/providers/${id}`)
}

export async function testCicdProvider(id: number): Promise<CicdProviderTestResult> {
  const { data } = await http.post<Result<CicdProviderTestResult>>(`/cicd/providers/${id}/test`)
  return data.data
}
