import http from './http'
import type { Result, Page, HostOut, HostCreate, HostUpdate, GroupOut, GroupCreate, GroupUpdate, CredentialOut, CredentialCreate, CredentialUpdate, HostStats, ConnectionResult, OptionsOut } from './types'

export async function getHosts(params?: {
  hostname?: string
  ip?: string
  os_type?: string
  group_id?: number
  env?: string
  tag?: string
  status?: string
  connector?: string
  page?: number
  size?: number
}): Promise<Page<HostOut>> {
  const { data } = await http.get<Result<Page<HostOut>>>('/assets/hosts', { params })
  return data.data
}

export async function getHost(id: number): Promise<HostOut> {
  const { data } = await http.get<Result<HostOut>>(`/assets/hosts/${id}`)
  return data.data
}

export async function createHost(payload: HostCreate): Promise<HostOut> {
  const { data } = await http.post<Result<HostOut>>('/assets/hosts', payload)
  return data.data
}

export async function updateHost(id: number, payload: HostUpdate): Promise<void> {
  await http.put<Result<void>>(`/assets/hosts/${id}`, payload)
}

export async function deleteHost(id: number): Promise<void> {
  await http.delete<Result<void>>(`/assets/hosts/${id}`)
}

export async function importHosts(file: File): Promise<{ success: number; failed: Array<{ row: number; error: string }> }> {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await http.post<Result<{ success: number; failed: Array<{ row: number; error: string }> }>>('/assets/hosts/import', formData)
  return data.data
}

export async function exportHosts(): Promise<Blob> {
  const { data } = await http.get('/assets/hosts/export', { responseType: 'blob' })
  return data
}

export async function checkConnection(id: number): Promise<ConnectionResult> {
  const { data } = await http.post<Result<ConnectionResult>>(`/assets/hosts/${id}/conn`)
  return data.data
}

export async function getGroupsTree(): Promise<GroupOut[]> {
  const { data } = await http.get<Result<GroupOut[]>>('/assets/groups/tree')
  return data.data
}

export async function createGroup(payload: GroupCreate): Promise<GroupOut> {
  const { data } = await http.post<Result<GroupOut>>('/assets/groups', payload)
  return data.data
}

export async function updateGroup(id: number, payload: GroupUpdate): Promise<void> {
  await http.put<Result<void>>(`/assets/groups/${id}`, payload)
}

export async function deleteGroup(id: number): Promise<void> {
  await http.delete<Result<void>>(`/assets/groups/${id}`)
}

export async function getCredentials(): Promise<CredentialOut[]> {
  const { data } = await http.get<Result<CredentialOut[]>>('/assets/credentials')
  return data.data
}

export async function createCredential(payload: CredentialCreate): Promise<CredentialOut> {
  const { data } = await http.post<Result<CredentialOut>>('/assets/credentials', payload)
  return data.data
}

export async function updateCredential(id: number, payload: CredentialUpdate): Promise<void> {
  await http.put<Result<void>>(`/assets/credentials/${id}`, payload)
}

export async function deleteCredential(id: number): Promise<void> {
  await http.delete<Result<void>>(`/assets/credentials/${id}`)
}

export async function getHostStats(): Promise<HostStats> {
  const { data } = await http.get<Result<HostStats>>('/assets/hosts/stats')
  return data.data
}

export async function getOptions(): Promise<OptionsOut> {
  const { data } = await http.get<Result<OptionsOut>>('/assets/options')
  return data.data
}