import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listApprovals,
  getApproval,
  approveApproval,
  rejectApproval,
  cancelApproval,
  listRules,
  createRule,
  updateRule,
  deleteRule,
} from '../src/api/approval'
import {
  listChannels,
  createChannel,
  updateChannel,
  deleteChannel,
  setChannelStatus,
  testChannel as sendChannelTest,
  listRecords,
  resendRecord,
} from '../src/api/notify'
import {
  listTerminals,
  createTerminal,
  getTerminal,
  getTerminalToken,
  closeTerminal,
  getRecording,
} from '../src/api/terminals'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function ok(data: unknown) {
  return { data: { code: 0, message: 'ok', data } }
}

describe('Approval API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists approvals with mine/todo bool filters', async () => {
    const page = { list: [{ id: 1, request_no: 'AP-1' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listApprovals({ status: 'pending', mine: true, todo: false, page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/approvals', {
      params: { status: 'pending', mine: true, todo: false, page: 1, size: 10 },
    })
    expect(result).toEqual(page)
  })

  it('fetches approval detail', async () => {
    const detail = { id: 5, request_no: 'AP-5', timeline: [] as never[] }
    vi.mocked(http.get).mockResolvedValue(ok(detail))
    const result = await getApproval(5)
    expect(http.get).toHaveBeenCalledWith('/approvals/5')
    expect(result).toEqual(detail)
  })

  it('approves with comment', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(null))
    await approveApproval(5, { comment: 'ok' })
    expect(http.post).toHaveBeenCalledWith('/approvals/5/approve', { comment: 'ok' })
  })

  it('rejects with comment', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(null))
    await rejectApproval(5, { comment: 'no' })
    expect(http.post).toHaveBeenCalledWith('/approvals/5/reject', { comment: 'no' })
  })

  it('cancels without a request body', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(null))
    await cancelApproval(5)
    expect(http.post).toHaveBeenCalledWith('/approvals/5/cancel')
  })

  it('lists rules', async () => {
    const rules = [{ id: 1, name: 'rm', kind: 'keyword', value: {}, enabled: 1 }]
    vi.mocked(http.get).mockResolvedValue(ok(rules))
    const result = await listRules()
    expect(http.get).toHaveBeenCalledWith('/approvals/rules')
    expect(result).toEqual(rules)
  })

  it('creates a rule', async () => {
    const rule = { id: 2, name: 'n', kind: 'count', value: { count: 50 }, enabled: 1 }
    vi.mocked(http.post).mockResolvedValue(ok(rule))
    const payload = { name: 'n', kind: 'count', value: { count: 50 }, enabled: 1 }
    const result = await createRule(payload)
    expect(http.post).toHaveBeenCalledWith('/approvals/rules', payload)
    expect(result).toEqual(rule)
  })

  it('updates a rule', async () => {
    vi.mocked(http.put).mockResolvedValue(ok(null))
    await updateRule(2, { name: 'n2', kind: 'keyword', value: { keywords: ['rm'] } })
    expect(http.put).toHaveBeenCalledWith('/approvals/rules/2', {
      name: 'n2',
      kind: 'keyword',
      value: { keywords: ['rm'] },
    })
  })

  it('deletes a rule', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok(null))
    await deleteRule(2)
    expect(http.delete).toHaveBeenCalledWith('/approvals/rules/2')
  })
})

describe('Notify API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists channels', async () => {
    const channels = [{ id: 1, name: 'lark', type: 'lark', enabled: 1, config_mask: {} }]
    vi.mocked(http.get).mockResolvedValue(ok(channels))
    const result = await listChannels()
    expect(http.get).toHaveBeenCalledWith('/notify/channels')
    expect(result).toEqual(channels)
  })

  it('creates a channel (secret write-only)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 9 }))
    await createChannel({ name: 'c', type: 'lark', config: { webhook: 'w', secret: 's' }, enabled: 1 })
    expect(http.post).toHaveBeenCalledWith('/notify/channels', {
      name: 'c',
      type: 'lark',
      config: { webhook: 'w', secret: 's' },
      enabled: 1,
    })
  })

  it('updates a channel', async () => {
    vi.mocked(http.put).mockResolvedValue(ok(null))
    await updateChannel(9, { name: 'c2', enabled: 0 })
    expect(http.put).toHaveBeenCalledWith('/notify/channels/9', { name: 'c2', enabled: 0 })
  })

  it('deletes a channel', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok(null))
    await deleteChannel(9)
    expect(http.delete).toHaveBeenCalledWith('/notify/channels/9')
  })

  it('sets channel status', async () => {
    vi.mocked(http.put).mockResolvedValue(ok(null))
    await setChannelStatus(9, { enabled: 0 })
    expect(http.put).toHaveBeenCalledWith('/notify/channels/9/status', { enabled: 0 })
  })

  it('sends a test message', async () => {
    const rec = { id: 3, status: 'success' }
    vi.mocked(http.post).mockResolvedValue(ok(rec))
    const result = await sendChannelTest(9, { title: 't', content: 'c' })
    expect(http.post).toHaveBeenCalledWith('/notify/channels/9/test', { title: 't', content: 'c' })
    expect(result).toEqual(rec)
  })

  it('lists records with query params', async () => {
    const page = { list: [{ id: 1, status: 'failed' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listRecords({ status: 'failed', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/notify/records', {
      params: { status: 'failed', page: 1, size: 10 },
    })
    expect(result).toEqual(page)
  })

  it('resends a failed record', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 3, status: 'success' }))
    await resendRecord(3)
    expect(http.post).toHaveBeenCalledWith('/notify/records/3/resend')
  })
})

describe('Terminal API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists terminals with query params', async () => {
    const page = { list: [{ id: 1, session_no: 'S-1' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listTerminals({ status: 'active', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/terminals', {
      params: { status: 'active', page: 1, size: 10 },
    })
    expect(result).toEqual(page)
  })

  it('creates a terminal session', async () => {
    const out = { id: 1, session_no: 'S-1', host_id: 5, status: 'active', sensitive: 0 }
    vi.mocked(http.post).mockResolvedValue(ok(out))
    const result = await createTerminal({ host_id: 5, reason: 'ops' })
    expect(http.post).toHaveBeenCalledWith('/terminals', { host_id: 5, reason: 'ops' })
    expect(result).toEqual(out)
  })

  it('fetches a terminal session', async () => {
    vi.mocked(http.get).mockResolvedValue(ok({ id: 1, session_no: 'S-1' }))
    const result = await getTerminal(1)
    expect(http.get).toHaveBeenCalledWith('/terminals/1')
    expect(result).toEqual({ id: 1, session_no: 'S-1' })
  })

  it('fetches a ws token for a session', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ session_id: 1, ws_token: 't', expires_in: 300 }))
    const result = await getTerminalToken(1)
    expect(http.post).toHaveBeenCalledWith('/terminals/1/token')
    expect(result.ws_token).toBe('t')
  })

  it('closes a terminal session', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(null))
    await closeTerminal(1)
    expect(http.post).toHaveBeenCalledWith('/terminals/1/close')
  })

  it('fetches recording replay with offset cursor', async () => {
    vi.mocked(http.get).mockResolvedValue(ok({ session_id: 1, after_offset: 5, has_more: false, chunks: [] }))
    const result = await getRecording(1, 0, 100)
    expect(http.get).toHaveBeenCalledWith('/terminals/1/recording', {
      params: { after_offset: 0, size: 100 },
    })
    expect(result.after_offset).toBe(5)
  })
})
