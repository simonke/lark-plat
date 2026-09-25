import http from './http'
import type { Result, Page, Release, ReleaseCreate, ReleaseQuery } from './types'

export async function listReleases(params?: ReleaseQuery): Promise<Page<Release>> {
  const { data } = await http.get<Result<Page<Release>>>('/releases', { params })
  return data.data
}

export async function createRelease(payload: ReleaseCreate): Promise<Release> {
  const { data } = await http.post<Result<Release>>('/releases', payload)
  return data.data
}

export async function getRelease(id: number): Promise<Release> {
  const { data } = await http.get<Result<Release>>(`/releases/${id}`)
  return data.data
}

export async function canaryRelease(id: number): Promise<Release> {
  const { data } = await http.post<Result<Release>>(`/releases/${id}/canary`)
  return data.data
}

export async function promoteRelease(id: number): Promise<Release> {
  const { data } = await http.post<Result<Release>>(`/releases/${id}/promote`)
  return data.data
}

export async function rollbackRelease(id: number): Promise<Release> {
  const { data } = await http.post<Result<Release>>(`/releases/${id}/rollback`)
  return data.data
}

export async function cancelRelease(id: number): Promise<Release> {
  const { data } = await http.post<Result<Release>>(`/releases/${id}/cancel`)
  return data.data
}
