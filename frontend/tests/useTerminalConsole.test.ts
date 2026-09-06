import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'
import { useTerminalConsole } from '../src/composables/useTerminalConsole'
import { getTerminalToken } from '../src/api/terminals'

vi.mock('../src/api/terminals', () => ({
  getTerminalToken: vi.fn()
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

const mockedGetTerminalToken = vi.mocked(getTerminalToken)

async function flush(times = 6) {
  for (let i = 0; i < times; i++) {
    await new Promise((r) => setTimeout(r, 0))
  }
}

describe('useTerminalConsole', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.resetAllMocks()
    mockedGetTerminalToken.mockResolvedValue({ session_id: 7, session_no: 'T-7', ws_token: 'tok-1', expires_in: 300 })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function startSession(overrides?: Partial<Parameters<typeof useTerminalConsole>[0]>) {
    const scope = effectScope()
    let session: ReturnType<typeof useTerminalConsole>
    scope.run(() => {
      session = useTerminalConsole({
        sessionId: 7,
        backoffBaseMs: 1,
        maxBackoffMs: 4,
        ...overrides,
      })
    })
    return { scope, session: session! }
  }

  it('provisions token and connects to the terminal WS with initial resize', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()

    expect(mockedGetTerminalToken).toHaveBeenCalledWith(7)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toContain('/api/v1/ws/terminal/7?token=tok-1')

    FakeWebSocket.instances[0].open()
    await flush()
    expect(session.connected.value).toBe(true)
    expect(JSON.parse(FakeWebSocket.instances[0].sent[0])).toEqual({
      type: 'resize',
      data: { cols: 120, rows: 40 },
    })
    scope.stop()
  })

  it('appends output frames in offset order and drops stale/duplicate offsets', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'output', data: { data: 'hello', offset: 1 } })
    ws.serverPush({ type: 'output', data: { data: '\r\n', offset: 3 } })
    ws.serverPush({ type: 'output', data: { data: 'stale', offset: 2 } })
    ws.serverPush({ type: 'output', data: { data: 'dup', offset: 3 } })
    ws.serverPush({ type: 'output', data: { data: '$ ', offset: 5 } })

    expect(session.buffer.value).toBe('hello\r\n$ ')
    scope.stop()
  })

  it('encodes input frames for the server when open', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()
    ws.sent.length = 0

    session.sendInput('ls -la\r')
    expect(JSON.parse(ws.sent[0])).toEqual({ type: 'input', data: { data: 'ls -la\r' } })
    scope.stop()
  })

  it('resends resize with new geometry when open', async () => {
    const { session, scope } = startSession({ cols: 100, rows: 30 })
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()
    ws.sent.length = 0

    session.resize(160, 40)
    expect(JSON.parse(ws.sent[0])).toEqual({ type: 'resize', data: { cols: 160, rows: 40 } })
    scope.stop()
  })

  it('reports non-open status frames and stops', async () => {
    const onStatus = vi.fn()
    const { session, scope } = startSession({ onStatus })
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'status', data: { status: 'idle_timeout' } })
    expect(onStatus).toHaveBeenCalledWith('idle_timeout')
    expect(session.connected.value).toBe(false)

    ws.serverClose(1001)
    await flush(20)
    expect(FakeWebSocket.instances).toHaveLength(1)
    scope.stop()
  })

  it('reconnects with a fresh token after close 4401', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const first = FakeWebSocket.instances[0]
    first.open()
    mockedGetTerminalToken.mockResolvedValue({
      session_id: 7,
      session_no: 'T-7',
      ws_token: 'tok-2',
      expires_in: 300,
    })

    first.serverClose(4401)
    await flush(20)

    expect(mockedGetTerminalToken).toHaveBeenCalledTimes(2)
    expect(FakeWebSocket.instances.length).toBeGreaterThanOrEqual(2)
    expect(FakeWebSocket.instances[1].url).toContain('token=tok-2')
    scope.stop()
  })

  it('stops permanently on close 4404 (session gone)', async () => {
    const { scope, session } = startSession()
    session.start()
    await flush()
    FakeWebSocket.instances[0].serverClose(4404)
    await flush(20)

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(session.connected.value).toBe(false)
    scope.stop()
  })

  it('stop() closes the socket and prevents further reconnects', async () => {
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
})