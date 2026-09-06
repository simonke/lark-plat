/**
 * useRealtimeLog — unified exec realtime log composable (contract api-design v2.1 §5/§14)
 *
 * Frozen scheme:
 * - ws-token exchange (REST) -> WS /api/v1/ws/exec/{task_host_id}?token=<jwt>
 * - token is handshake-only (5min JWT bound to task_host_id); connection persists for the task
 * - REST GET .../logs?after_seq=N is the replay source of truth ({list, next_seq})
 * - close codes: 4401 = token invalid/expired (re-exchange token, reconnect), 4404 = task host gone (stop)
 * - client keepalive: {type:"ping"} -> {type:"pong"}; server may push {type:"status"}
 * - seq ordering: frames only accepted when seq > lastSeq; any gap triggers REST backfill
 */
import { ref, onScopeDispose } from 'vue'
import { getLogs, getWsToken } from '../api/exec'
import type { ExecLogOut } from '../api/types'

export interface RealtimeLogFrame {
  type: 'log' | 'status' | 'pong' | string
  data: Record<string, unknown>
}

export interface UseRealtimeLogOptions {
  taskId: number
  taskHostId: number
  /** keepalive interval ms (default 30s, protocol allows <=30s heartbeat cadence) */
  pingIntervalMs?: number
  /** reconnect backoff base ms (default 1s, doubles up to maxBackoffMs) */
  backoffBaseMs?: number
  maxBackoffMs?: number
  onStatus?: (status: string) => void
}

/** ws open guard: a CONNECTING socket that never opens within this window is closed and retried. */
export const OPEN_TIMEOUT_MS = 8000

export function useRealtimeLog(options: UseRealtimeLogOptions) {
  const {
    taskId,
    taskHostId,
    pingIntervalMs = 30_000,
    backoffBaseMs = 1_000,
    maxBackoffMs = 15_000,
    onStatus,
  } = options

  const lines = ref<ExecLogOut[]>([])
  const connected = ref(false)
  const closed = ref(false)

  let lastSeq = 0
  let socket: WebSocket | null = null
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let connecting = false

  function appendBatch(batch: ExecLogOut[]): void {
    for (const line of batch) {
      if (line.seq > lastSeq) {
        lines.value.push(line)
        lastSeq = line.seq
      }
    }
  }

  /** REST replay from lastSeq until drained; returns true when caught up. */
  async function backfill(): Promise<void> {
    for (;;) {
      const prevSeq = lastSeq
      const page = await getLogs(taskId, taskHostId, lastSeq, 500)
      appendBatch(page.list)
      // keep fetching only when this page actually advanced the cursor
      if (page.list.length === 0 || page.next_seq <= prevSeq) return
    }
  }

  function startPing(): void {
    stopPing()
    pingTimer = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'ping' }))
      }
    }, pingIntervalMs)
  }

  function stopPing(): void {
    if (pingTimer !== null) {
      clearInterval(pingTimer)
      pingTimer = null
    }
  }

  async function connect(): Promise<void> {
    if (closed.value || connecting) return
    connecting = true
    try {
      // history/incremental replay first so nothing is missed before WS attach
      await backfill()
      const token = await getWsToken(taskId, taskHostId)
      await new Promise<void>((resolve, reject) => {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const ws = new WebSocket(
          `${proto}://${window.location.host}/api/v1/ws/exec/${taskHostId}?token=${encodeURIComponent(token)}`,
        )
        socket = ws
        let openTimedOut = false
        // open guard: a socket stuck CONNECTING (proxy/firewall) must not hold the
        // session forever; close -> reject so the caller schedules a backoff retry
        const openTimer = setTimeout(() => {
          if (ws.readyState === WebSocket.CONNECTING) {
            openTimedOut = true
            connected.value = false
            ws.close(1000)
            reject(new Error('websocket open timeout'))
          }
        }, OPEN_TIMEOUT_MS)
        ws.onopen = () => {
          clearTimeout(openTimer)
          if (openTimedOut) return
          attempt = 0
          connected.value = true
          startPing()
          resolve()
        }
        ws.onmessage = (ev: MessageEvent<string>) => {
          let frame: RealtimeLogFrame
          try {
            frame = JSON.parse(ev.data) as RealtimeLogFrame
          } catch {
            return
          }
          if (frame.type === 'log') {
            const entry = frame.data as unknown as ExecLogOut
            if (typeof entry?.seq === 'number') {
              if (entry.seq > lastSeq) {
                // tolerate single-step frames; larger jumps fall back to REST replay
                if (entry.seq === lastSeq + 1) {
                  lines.value.push(entry)
                  lastSeq = entry.seq
                } else {
                  void backfill()
                }
              }
            }
          } else if (frame.type === 'status') {
            const status = typeof frame.data?.status === 'string' ? frame.data.status : undefined
            if (status !== undefined) onStatus?.(status)
          }
          // pong frames need no handling; liveness is implied by open socket
        }
        ws.onclose = (ev: CloseEvent) => {
          clearTimeout(openTimer)
          connected.value = false
          stopPing()
          socket = null
          if (openTimedOut) return
          if (ev.code === 4404) {
            closed.value = true
            reject(new Error('task host not found'))
            return
          }
          if (!closed.value) scheduleReconnect(ev.code === 4401)
          resolve()
        }
        ws.onerror = () => {
          if (openTimedOut) return
          if (ws.readyState !== WebSocket.CONNECTING) return
          connected.value = false
          reject(new Error('websocket connect failed'))
        }
      })
    } finally {
      connecting = false
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
    void connect().catch(() => scheduleReconnect(true))
  }

  function stop(): void {
    closed.value = true
    stopPing()
    if (retryTimer !== null) {
      clearTimeout(retryTimer)
      retryTimer = null
    }
    if (socket !== null) {
      socket.onclose = null
      socket.close(1000)
      socket = null
    }
    connected.value = false
  }

  onScopeDispose(stop)

  return { lines, connected, start, stop }
}
