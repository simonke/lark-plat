import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { effectScope } from 'vue'
import { useWorkflowRunRealtime } from '../src/composables/useWorkflowRunRealtime'
import { getWorkflowRun, getWorkflowRunWsToken } from '../src/api/workflow'
import type { WorkflowNodeRun, WorkflowRun, WorkflowRunDetail } from '../src/api/types'

vi.mock('../src/api/workflow', () => ({
  getWorkflowRun: vi.fn(),
  getWorkflowRunWsToken: vi.fn(),
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

const mockedGetRun = vi.mocked(getWorkflowRun)
const mockedGetWsToken = vi.mocked(getWorkflowRunWsToken)

function runOut(status: WorkflowRun['status'] = 'running', id = 9): WorkflowRun {
  return {
    id,
    workflow_id: 5,
    workflow_version: 1,
    status,
    trigger_type: 'manual',
    trigger_ref: null,
    context: null,
    started_at: 't',
    finished_at: null,
    error: null,
    created_by: 1,
    created_at: 't',
  }
}

function nodeOut(node_key: string, status: WorkflowNodeRun['status'] = 'running'): WorkflowNodeRun {
  return {
    id: 1,
    run_id: 9,
    node_key,
    node_type: 'exec_task',
    status,
    exec_task_id: null,
    approval_id: null,
    attempt: 0,
    output: null,
    error: null,
    started_at: 't',
    finished_at: null,
  }
}

function detail(status: WorkflowRun['status'] = 'running', nodes: WorkflowNodeRun[] = []): WorkflowRunDetail {
  return { run: runOut(status), nodes }
}

async function flush(times = 6) {
  for (let i = 0; i < times; i++) {
    await new Promise((r) => setTimeout(r, 0))
  }
}

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled'])

describe('useWorkflowRunRealtime', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.resetAllMocks()
    mockedGetRun.mockResolvedValue(detail('running', [nodeOut('a')]))
    mockedGetWsToken.mockResolvedValue('token-1')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function startSession() {
    const scope = effectScope()
    const runs: WorkflowRun[] = []
    const nodes: WorkflowNodeRun[] = []
    let session: ReturnType<typeof useWorkflowRunRealtime>
    scope.run(() => {
      session = useWorkflowRunRealtime({
        runId: 9,
        pingIntervalMs: 5,
        backoffBaseMs: 1,
        maxBackoffMs: 4,
        onRun: (r) => runs.push(r),
        onNode: (n) => nodes.push(n),
        isTerminal: (r) => TERMINAL.has(r.status),
      })
    })
    return { scope, session: session!, runs, nodes }
  }

  it('replays run detail via REST then attaches WS with the exchanged ws-token', async () => {
    const { session, scope, runs, nodes } = startSession()
    session.start()
    await flush()

    expect(mockedGetRun).toHaveBeenCalledWith(9)
    expect(mockedGetWsToken).toHaveBeenCalledWith(9)
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(FakeWebSocket.instances[0].url).toContain('/api/v1/ws/workflow-runs/9?token=token-1')
    expect(runs[0].id).toBe(9)
    expect(nodes.map((n) => n.node_key)).toEqual(['a'])

    FakeWebSocket.instances[0].open()
    await flush()
    expect(session.connected.value).toBe(true)
    scope.stop()
  })

  it('treats a run frame as a notification (top-level seq) and REST re-syncs state', async () => {
    mockedGetRun
      .mockResolvedValueOnce(detail('running', [nodeOut('a')]))
      .mockResolvedValueOnce(detail('succeeded', [nodeOut('a', 'succeeded')]))

    const { session, scope, runs } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'run', data: { run_id: 9 }, seq: 1 })
    await flush()

    expect(mockedGetRun).toHaveBeenCalledTimes(2)
    expect(runs[runs.length - 1].status).toBe('succeeded')
    scope.stop()
  })

  it('drops stale/duplicate seq frames (no redundant re-sync)', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'run', data: { run_id: 9 }, seq: 1 })
    await flush()
    ws.serverPush({ type: 'run', data: { run_id: 9 }, seq: 1 })
    ws.serverPush({ type: 'run', data: { run_id: 9 }, seq: 0 })
    await flush()

    expect(mockedGetRun).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('ignores pong frames (keepalive only)', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'pong', seq: 1 })
    await flush()

    expect(mockedGetRun).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('ignores reserved/unknown frame types (node is reserve in P3-4, tuple G)', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    const ws = FakeWebSocket.instances[0]
    ws.open()

    ws.serverPush({ type: 'node', data: { node_key: 'a' }, seq: 1 })
    ws.serverPush({ type: 'whatever', seq: 2 })
    await flush()

    expect(mockedGetRun).toHaveBeenCalledTimes(1)
    scope.stop()
  })

  it('stops without attaching WS when the run is already terminal', async () => {
    mockedGetRun.mockResolvedValue(detail('succeeded'))

    const { session, scope } = startSession()
    session.start()
    await flush()

    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(session.connected.value).toBe(false)
    scope.stop()
  })

  it('reconnects with a fresh ws-token after close 4401', async () => {
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

  it('stops permanently on close 4404 (run gone)', async () => {
    const { session, scope } = startSession()
    session.start()
    await flush()
    FakeWebSocket.instances[0].serverClose(4404)
    await flush(20)

    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(session.connected.value).toBe(false)
    scope.stop()
  })
})
