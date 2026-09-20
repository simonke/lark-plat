/**
 * useTransferRealtimeLog — file-distribution realtime log composable (contract api-design §1)
 *
 * Mirrors exec's useRealtimeLog but wired to the /transfer contract:
 * - ws-token exchange (REST GET /transfer/tasks/{task_id}/hosts/{thid}/ws-token, 5min JWT)
 *   -> WS /api/v1/ws/transfer/{transfer_host_id}?token=<jwt>
 * - REST GET .../logs?after_seq=N is the replay source of truth ({list, next_seq})
 * - close codes: 4401 = token invalid/expired (re-exchange, reconnect), 4404 = host gone (stop)
 * - keepalive: {type:"ping"} -> {type:"pong"}; server may push {type:"status"}
 * - seq ordering: frames accepted only when seq > lastSeq; gaps trigger REST backfill
 */
import { ref, onScopeDispose } from 'vue'
import { getTransferLogs, getTransferWsToken } from '../api/transfer'
import type { TransferLogOut } from '../api/types'

export interface TransferRealtimeLogFrame {
  type: 'log' | 'status' | 'pong' | string
  data: Record<string, unknown>
}

export interface UseTransferRealtimeLogOptions {
  taskId: number
  transferHostId: number
  pingIntervalMs?: number
  backoffBaseMs?: number
  maxBackoffMs?: number
  onStatus?: (status: string) => void
}

export const OPEN_TIMEOUT_MS = 8000

export function useTransferRealtimeLog(options: UseTransferRealtimeLogOptions) {
  const {
    taskId,
    transferHostId,
    pingIntervalMs = 30_000,
    backoffBaseMs = 1_000,
    maxBackoffMs = 15_000,
    onStatus,
  } = options

  const lines = ref<TransferLogOut[]>([])
  const connected = ref(false)
  const closed = ref(false)

  let lastSeq = 0
  let socket: WebSocket | null = null
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let connecting = false

  function appendBatch(batch: TransferLogOut[]): void {
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
      const page = await getTransferLogs(taskId, transferHostId, lastSeq, 500)
      appendBatch(page.list)
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
      await backfill()
      const token = await getTransferWsToken(taskId, transferHostId)
      await new Promise<void>((resolve, reject) => {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const ws = new WebSocket(
          `${proto}://${window.location.host}/api/v1/ws/transfer/${transferHostId}?token=${encodeURIComponent(token)}`,
        )
        socket = ws
        let openTimedOut = false
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
          let frame: TransferRealtimeLogFrame
          try {
            frame = JSON.parse(ev.data) as TransferRealtimeLogFrame
          } catch {
            return
          }
          if (frame.type === 'log') {
            const entry = frame.data as unknown as TransferLogOut
            if (typeof entry?.seq === 'number') {
              if (entry.seq > lastSeq) {
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
        }
        ws.onclose = (ev: CloseEvent) => {
          clearTimeout(openTimer)
          connected.value = false
          stopPing()
          socket = null
          if (openTimedOut) return
          if (ev.code === 4404) {
            closed.value = true
            reject(new Error('transfer host not found'))
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