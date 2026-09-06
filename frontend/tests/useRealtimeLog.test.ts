import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'
import { useRealtimeLog, OPEN_TIMEOUT_MS } from '../src/composables/useRealtimeLog'
import { getLogs, getWsToken } from '../src/api/exec'

vi.mock('../src/api/exec', () => ({
  getLogs: vi.fn(),
  getWsToken: vi.fn()
}))

class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances: FakeWebSocket[] = []
  url: string
  readyState = 0
  sent: string[] = []
  closeCode: number | null = null
  onopen: (() => void) | null = null
  onclose: ((ev: { code: number }) => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close(code = 1000) {
    this.closeCode = code
  }
  open() {
    this.readyState = 1
    this.onopen?.()
  }
  serverPush(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }
  serverClose(code: number) {
    this.readyState = 3
    this.onclose?.({ code } as CloseEvent)
  }
}

const mockedGetLogs = vi.mocked(getLogs)
const mockedGetWsToken = vi.mocked(getWsToken)

function logLine(seq: number, content = `line-${seq}`) {
  return { seq, level: 'info', content, created_at: '2026-08-25 10:00:00' }
}

async function flush(times = 6) {
  for (let i = 0; i < times; i++) {
    await new Promise((r) => setTimeout(r, 0))
  }
}

describe('useRealtimeLog', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.resetAllMocks()
    mockedGetLogs.mockResolvedValue({ list: [], next_seq: 0 })
    mockedGetWsToken.mockResolvedValue('token-1')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function startSession(overrides?: Partial<Parameters<typeof useRealtimeLog>[0]>) {
    const scope = effectScope()
    let session: ReturnType<typeof useRealtimeLog>
    scope.run(() => {
      session = useRealtimeLog({
        taskId: 5,
        taskHostId: 51,
        pingIntervalMs: 5,
        backoffBaseMs: 1,
        maxBackoffMs: 4,
        ...overrides,
      })
    })
    return { scope, session: session! }
  }

  it('replays history via REST (after_seq=0) before attaching WS with exchanged token', async () => {
    mockedGetLogs.mockResolvedValue({ list: [logLine(1), logLine(2)], next_seq: 2 })

    const { session, scope } = startSession()
    session.start()
    await flush()

    expect(mockedGetLogs).toHaveBeenCalledWith(5, 51, 0, 500)
    expect(mockedGetWsToken).toHaveBeenCalledWith(5, 51)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toContain('/api/v1/ws/exec/51?token=token-1')
    expect(session.lines.value.map((l) => l.seq)).toEqual([1, 2])
    FakeWebSocket.instances[0].open()
    await flush()
    expect(session.connected.value).toBe(true)
    scope.stop()
  })

  it('keeps draining history until caught up (multi-page backfill)', async () => {
    mockedGetLogs
      .mockResolvedValueOnce({ list: [logLine(1), logLine(2)], next_seq: 2 })
      .mockResolvedValueOnce({ list: [logLine(3)], next_seq: 3 })
      .mockResolvedValueOnce({ list: [], next_seq: 3 })

    const { session, scope } = startSession()
    session.start()
    await flush()

    expect(mockedGetLogs).toHaveBeenCalledTimes(3)
    expect(mockedGetLogs).toHaveBeenNthCalledWith(2, 5, 51, 2, 500)
    expect(mockedGetLogs).toHaveBeenNthCalledWith(3, 5, 51, 3, 500)
    expect(session.lines.value.map((l) => l.seq)).toEqual([1, 2, 3])
    scope.stop()
  })

  it('accepts in-order single-step WS frames and ignores stale/duplicate seqs', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'log', data: logLine(1) })
    ws.serverPush({ type: 'log', data: logLine(2) })
    ws.serverPush({ type: 'log', data: logLine(2) })

    expect(session.lines.value.map((l) => l.seq)).toEqual([1, 2])
    scope.stop()
  })

  it('falls back to REST replay on seq jump (gap protection)', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'log', data: logLine(1) })
    ws.serverPush({ type: 'log', data: logLine(9) })
    await flush()

    expect(mockedGetLogs).toHaveBeenCalledWith(5, 51, 1, 500)
    expect(session.lines.value.map((l) => l.seq)).toEqual([1])
    scope.stop()
  })

  it('reconnects with a fresh token after close 4401', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const first = FakeWebSocket.instances[0]
    first.open()
    mockedGetWsToken.mockResolvedValue('token-2')

    first.serverClose(4401)
    await flush(20)

    expect(mockedGetWsToken).toHaveBeenCalledTimes(2)
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2)
    expect(FakeWebSocket.instances[1].url).toContain('token=token-2')
    expect(session.connected.value).toBe(false)
    scope.stop()
  })

  it('stops permanently on close 4404 (task host gone)', async () => {
    const { scope, session } = startSession()
    session.start()
    await flush()
    FakeWebSocket.instances[0].serverClose(4404)
    await flush(20)

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(session.connected.value).toBe(false)
    scope.stop()
  })

  it('stop() closes socket and prevents further reconnect attempts', async () => {
    const { scope, session } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    session.stop()
    expect(ws.closeCode).toBe(1000)

    ws.serverClose(1001)
    await flush(20)
    expect(FakeWebSocket.instances).toHaveLength(1)
    scope.stop()
  })

  it('sends protocol keepalive ping frames while connected', async () => {
    vi.useFakeTimers()
    try {
      const { scope, session } = startSession({ pingIntervalMs: 10 })
      session.start()
      await vi.advanceTimersByTimeAsync(0)
      const ws = FakeWebSocket.instances[0]
      ws.open()

      await vi.advanceTimersByTimeAsync(35)

      const pings = ws.sent.filter((m) => JSON.parse(m).type === 'ping')
      expect(pings.length).toBe(3)
      scope.stop()
    } finally {
      vi.useRealTimers()
    }
  })

  it('closes and backoff-reconnects when the socket never opens within the open timeout', async () => {
    vi.useFakeTimers()
    try {
      const { scope, session } = startSession()
      session.start()
      await vi.advanceTimersByTimeAsync(0)
      const first = FakeWebSocket.instances[0]
      expect(first.readyState).toBe(0)
      expect(session.connected.value).toBe(false)

      // no onopen -> open guard fires at OPEN_TIMEOUT_MS
      await vi.advanceTimersByTimeAsync(OPEN_TIMEOUT_MS)

      expect(first.closeCode).toBe(1000)

      // caller catch schedules backoff retry (base 1ms) -> a fresh socket appears
      await vi.advanceTimersByTimeAsync(20)
      expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2)
      expect(session.connected.value).toBe(false)
      scope.stop()
    } finally {
      vi.useRealTimers()
    }
  })

  it('clears the open timeout on successful onopen (no spurious close or reconnect)', async () => {
    vi.useFakeTimers()
    try {
      const { scope, session } = startSession()
      session.start()
      await vi.advanceTimersByTimeAsync(0)
      const ws = FakeWebSocket.instances[0]
      ws.open()
      expect(session.connected.value).toBe(true)

      // well past the guard window: still connected, single socket, no close
      await vi.advanceTimersByTimeAsync(OPEN_TIMEOUT_MS * 2)
      expect(ws.closeCode).toBeNull()
      expect(FakeWebSocket.instances).toHaveLength(1)
      expect(session.connected.value).toBe(true)
      scope.stop()
    } finally {
      vi.useRealTimers()
    }
  })
})
