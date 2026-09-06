/**
 * Script API — new file frontend/src/api/scripts.ts (stage 3 batch 1)
 * Contract: api-design v2.1 §4 (/scripts), shapes @ backend schemas e04d85e.
 */
import http from './http'
import type {
  Result,
  Page,
  ScriptOut,
  ScriptDetail,
  ScriptCreate,
  ScriptUpdate,
  ScriptVersionOut,
  ScriptQuery,
  RollbackIn,
  ScriptTestIn,
  ScriptTestResult,
} from './types'

export async function getScripts(params?: ScriptQuery): Promise<Page<ScriptOut>> {
  const { data } = await http.get<Result<Page<ScriptOut>>>('/scripts', { params })
  return data.data
}

export async function getScript(id: number, version?: number): Promise<ScriptDetail> {
  const { data } = await http.get<Result<ScriptDetail>>(`/scripts/${id}`, {
    params: version !== undefined ? { version } : undefined,
  })
  return data.data
}

export async function createScript(payload: ScriptCreate): Promise<ScriptOut> {
  const { data } = await http.post<Result<ScriptOut>>('/scripts', payload)
  return data.data
}

export async function updateScript(id: number, payload: ScriptUpdate): Promise<void> {
  await http.put<Result<void>>(`/scripts/${id}`, payload)
}

export async function deleteScript(id: number): Promise<void> {
  await http.delete<Result<void>>(`/scripts/${id}`)
}

export async function getVersions(scriptId: number): Promise<ScriptVersionOut[]> {
  const { data } = await http.get<Result<ScriptVersionOut[]>>(`/scripts/${scriptId}/versions`)
  return data.data
}

export async function getVersion(scriptId: number, version: number): Promise<ScriptVersionOut> {
  const { data } = await http.get<Result<ScriptVersionOut>>(`/scripts/${scriptId}/versions/${version}`)
  return data.data
}

export async function rollbackScript(scriptId: number, payload: RollbackIn): Promise<void> {
  await http.post<Result<void>>(`/scripts/${scriptId}/rollback`, payload)
}

export async function testScript(scriptId: number, payload: ScriptTestIn): Promise<ScriptTestResult> {
  const { data } = await http.post<Result<ScriptTestResult>>(`/scripts/${scriptId}/test`, payload)
  return data.data
}
