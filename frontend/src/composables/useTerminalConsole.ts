/**
 * useTerminalConsole — live interactive terminal composable (contract api-design v2.1 §6.5)
 *
 * Frozen scheme:
 * - token provisioning (REST) POST /terminals/{session_id}/token -> {ws_token, expires_in}
 * - WS /api/v1/ws/terminal/{session_id}?token=<jwt> (handshake-only, bound to session_id)
 * - S->C: {type:"output", data:{data, offset, ts}} raw stream, offset strictly increasing
 * - S->C: {type:"status", data:{status:"open|closed|idle_timeout|duration_limit"}}
 * - C->S: {type:"input", data:{data}} and {type:"resize", data:{cols, rows}}
 * - close codes: 4401 = token invalid/expired (re-provision token), 4404 = session gone (stop)
 * - output frames accepted only when offset > lastOffset; stale/out-of-order frames dropped
 */
import { ref, onScopeDispose } from 'vue'
import { getTerminalToken } from '../api/terminals'

export interface TerminalConsoleFrame {
  type: 'output' | 'status' | string
  data: Record<string, unknown>
}

export interface UseTerminalConsoleOptions {
  sessionId: number
  cols?: number
  rows?: number
  /** reconnect backoff base ms (default 1s, doubles up to maxBackoffMs) */
  backoffBaseMs?: number
  maxBackoffMs?: number
  onStatus?: (status: string) => void
}

export function useTerminalConsole(options: UseTerminalConsoleOptions) {
  const {
    sessionId,
    cols = 120,
    rows = 40,
    backoffBaseMs = 1_000,
    maxBackoffMs = 15_000,
    onStatus,
  } = options

  const buffer = ref('')
  const connected = ref(false)
  const closed = ref(false)

  let lastOffset = 0
  let currentCols = cols
  let currentRows = rows
  let socket: WebSocket | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let connecting = false

  function appendOutput(data: string, offset: number): void {
    if (typeof data !== 'string' || typeof offset !== 'number') return
    if (offset > lastOffset) {
      buffer.value += data
      lastOffset = offset
    }
  }

  function sendInput(data: string): void {
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'input', data: { data } }))
    }
  }

  function resize(nextCols: number, nextRows: number): void {
    currentCols = nextCols
    currentRows = nextRows
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: 'resize', data: { cols: nextCols, rows: nextRows } }))
    }
  }

  async function connect(): Promise<void> {
    if (closed.value || connecting) return
    connecting = true
    try {
      const { ws_token } = await getTerminalToken(sessionId)
      await new Promise<void>((resolve, reject) => {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const ws = new WebSocket(
          `${proto}://${window.location.host}/api/v1/ws/terminal/${sessionId}?token=${encodeURIComponent(ws_token)}`,
        )
        socket = ws
        ws.onopen = () => {
          attempt = 0
          connected.value = true
          ws.send(JSON.stringify({ type: 'resize', data: { cols: currentCols, rows: currentRows } }))
          resolve()
        }
        ws.onmessage = (ev: MessageEvent<string>) => {
          let frame: TerminalConsoleFrame
          try {
            frame = JSON.parse(ev.data) as TerminalConsoleFrame
          } catch {
            return
          }
          if (frame.type === 'output') {
            const payload = frame.data as { data?: string; offset?: unknown }
            if (typeof payload?.data === 'string' && typeof payload.offset === 'number') {
              appendOutput(payload.data, payload.offset)
            }
          } else if (frame.type === 'status') {
            const status = typeof frame.data?.status === 'string' ? frame.data.status : undefined
            if (status !== undefined) {
              onStatus?.(status)
              if (status !== 'open') {
                closed.value = true
                connected.value = false
                stopTimers()
                ws.close(1000)
              }
            }
          }
        }
        ws.onclose = (ev: CloseEvent) => {
          connected.value = false
          socket = null
          if (ev.code === 4404) {
            closed.value = true
            stopTimers()
            reject(new Error('terminal session not found'))
            return
          }
          if (!closed.value) scheduleReconnect(ev.code === 4401)
          resolve()
        }
        ws.onerror = () => {
          if (ws.readyState !== WebSocket.CONNECTING) return
          connected.value = false
          reject(new Error('websocket connect failed'))
        }
      })
    } finally {
      connecting = false
    }
  }

  function stopTimers(): void {
    if (retryTimer !== null) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
  }

  /** 4401: force fresh token next round; others: plain backoff. */
  function scheduleReconnect(freshToken: boolean): void {
    if (freshToken) attempt = 0
    const delay = Math.min(backoffBaseMs * 2 ** attempt, maxBackoffMs)
    attempt += 1
    retryTimer = setTimeout(() => {
      void connect().catch(() => scheduleReconnect(false))
    }, delay)
  }

  function start(): void {
    closed.value = false
    lastOffset = 0
    buffer.value = ''
    void connect().catch(() => scheduleReconnect(true))
  }

  function stop(): void {
    closed.value = true
    stopTimers()
    if (socket !== null) {
      socket.onclose = null
      socket.close(1000)
      socket = null
    }
    connected.value = false
  }

  onScopeDispose(stop)

  return { buffer, connected, sendInput, resize, start, stop }
}