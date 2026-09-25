/**
 * useWorkflowRunRealtime — workflow run realtime (P3-4b engine tuple v1.1, seq2918 §G).
 *
 * Frozen scheme (P3-4b engine tuple v1.1/v1.2; impl @7bb583f):
 * - ws-token exchange (REST): GET /workflow-runs/{run_id}/ws-token -> {token}
 *   (5min JWT, sub=run_id, type="ws"; feature gate first -> workflow:view)
 * - WS full path: /api/v1/ws/workflow-runs/{run_id}?token=<jwt> (mounted under api_prefix)
 * - frames S->C: {type:"run", data:{"run_id":...}, seq:<n>} (seq at top level)
 *   and {type:"pong", seq:<n>}; C->S: {type:"ping"}.
 *   P3-4 emit set = run/pong; {type:"node"} is **reserved** and — like any unknown type —
 *   ignored (node-level realtime is delivered by a run frame + full-nodes REST re-sync).
 * - frames are **notifications** (data carries run_id only) — the authoritative state is
 *   fetched via REST GET /workflow-runs/{run_id}; each accepted run frame triggers a
 *   coalesced re-sync. seq is monotonic; frames with seq <= lastSeq are dropped.
 * - reconnect: REST replay first, then WS (seq resets on each (re)connect).
 * - close codes: 4401 = token invalid/expired (re-exchange token), 4404 = run gone (stop).
 */
import { ref, onScopeDispose } from 'vue'
import { getWorkflowRun, getWorkflowRunWsToken } from '../api/workflow'
import type { WorkflowNodeRun, WorkflowRun } from '../api/types'

export interface WorkflowRunFrame {
  type: 'run' | 'node' | 'pong' | string
  data?: Record<string, unknown>
  seq?: number
}

export interface UseWorkflowRunRealtimeOptions {
  runId: number
  /** keepalive interval ms (default 30s) */
  pingIntervalMs?: number
  /** reconnect backoff base ms (default 1s, doubles up to maxBackoffMs) */
  backoffBaseMs?: number
  maxBackoffMs?: number
  onRun?: (run: WorkflowRun) => void
  onNode?: (node: WorkflowNodeRun) => void
  /** fired when the run reaches a terminal status so callers may stop the stream */
  isTerminal?: (run: WorkflowRun) => boolean
}

/** ws open guard: a CONNECTING socket that never opens within this window is closed and retried. */
export const OPEN_TIMEOUT_MS = 8000

export function useWorkflowRunRealtime(options: UseWorkflowRunRealtimeOptions) {
  const {
    runId,
    pingIntervalMs = 30_000,
    backoffBaseMs = 1_000,
    maxBackoffMs = 15_000,
    onRun,
    onNode,
    isTerminal,
  } = options

  const connected = ref(false)
  const closed = ref(false)

  let lastSeq = 0
  let socket: WebSocket | null = null
  let pingTimer: ReturnType<typeof setInterval> | null = null
  let retryTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let connecting = false

  /** REST authoritative replay (run + nodes) before attaching WS. */
  async function replay(): Promise<void> {
    const detail = await getWorkflowRun(runId)
    onRun?.(detail.run)
    for (const node of detail.nodes) onNode?.(node)
    if (detail.run && isTerminal?.(detail.run)) stop()
  }

  let syncing = false

  /** Coalesced authoritative re-sync — frames are notifications, not state payloads. */
  async function syncFromFrame(): Promise<void> {
    if (syncing || closed.value) return
    syncing = true
    try {
      await replay()
    } catch {
      // transient REST blip: the next frame or reconnect covers it
    } finally {
      syncing = false
    }
  }

  function applyFrame(frame: WorkflowRunFrame): void {
    const seq =
      typeof frame.seq === 'number'
        ? frame.seq
        : typeof frame.data?.seq === 'number'
          ? (frame.data.seq as number)
          : undefined
    if (seq !== undefined) {
      if (seq <= lastSeq) return
      lastSeq = seq
    }
    // pong is keepalive only; a run frame triggers a REST re-sync.
    // "node" is reserved (not emitted in P3-4) and, with any unknown type, ignored.
    if (frame.type === 'run') {
      void syncFromFrame()
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
      await replay()
      if (closed.value) return
      const token = await getWorkflowRunWsToken(runId)
      await new Promise<void>((resolve, reject) => {
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
        const ws = new WebSocket(
          `${proto}://${window.location.host}/api/v1/ws/workflow-runs/${runId}?token=${encodeURIComponent(token)}`,
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
          lastSeq = 0
          connected.value = true
          startPing()
          resolve()
        }
        ws.onmessage = (ev: MessageEvent<string>) => {
          let frame: WorkflowRunFrame
          try {
            frame = JSON.parse(ev.data) as WorkflowRunFrame
          } catch {
            return
          }
          applyFrame(frame)
        }
        ws.onclose = (ev: CloseEvent) => {
          clearTimeout(openTimer)
          connected.value = false
          stopPing()
          socket = null
          if (openTimedOut) return
          if (ev.code === 4404) {
            closed.value = true
            reject(new Error('workflow run not found'))
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

  return { connected, start, stop }
}
