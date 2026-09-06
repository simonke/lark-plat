/**
 * Terminal API — new file frontend/src/api/terminals.ts (stage 4)
 * Contract: api-design v2.1 §6.5 (/terminals), shapes @ backend schemas.
 * REST flow: list/create/detail/token/close/recording(replay). The live
 * interactive console uses WSS /ws/terminal/{session_id}; this layer only
 * provisions the ws_token and reads the AES-GCM recording for replay.
 */
import http from './http'
import type {
  Page,
  Result,
  TerminalCreate,
  TerminalOut,
  TerminalRequestOut,
  TerminalTokenOut,
  TerminalRecordingOut,
  TerminalQuery,
} from './types'

export async function listTerminals(params?: TerminalQuery): Promise<Page<TerminalOut>> {
  const { data } = await http.get<Result<Page<TerminalOut>>>('/terminals', { params })
  return data.data
}

export async function createTerminal(payload: TerminalCreate): Promise<TerminalRequestOut> {
  const { data } = await http.post<Result<TerminalRequestOut>>('/terminals', payload)
  return data.data
}

export async function getTerminal(sessionId: number): Promise<TerminalOut> {
  const { data } = await http.get<Result<TerminalOut>>(`/terminals/${sessionId}`)
  return data.data
}

export async function getTerminalToken(sessionId: number): Promise<TerminalTokenOut> {
  const { data } = await http.post<Result<TerminalTokenOut>>(`/terminals/${sessionId}/token`)
  return data.data
}

export async function closeTerminal(sessionId: number): Promise<void> {
  await http.post<Result<void>>(`/terminals/${sessionId}/close`)
}

export async function getRecording(
  sessionId: number,
  afterOffset = 0,
  size = 100,
): Promise<TerminalRecordingOut> {
  const { data } = await http.get<Result<TerminalRecordingOut>>(`/terminals/${sessionId}/recording`, {
    params: { after_offset: afterOffset, size },
  })
  return data.data
}
