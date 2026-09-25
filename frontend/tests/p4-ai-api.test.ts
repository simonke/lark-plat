import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listEvents,
  getEvent,
  ticketSuggest,
  ticketSimilar,
  kbSearchSemantic,
  kbAnswer,
  aiFeedback,
  listAiActions,
} from '../src/api/ai'
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

const EVENT = {
  id: 11,
  ts: '2026-09-25T12:00:00',
  entity_type: 'host',
  entity_id: '10.0.0.1',
  action: 'restart',
  result: 'success',
  source: 'exec',
  refs: { task: 5 },
  trace_id: 'tr-1',
  created_at: '2026-09-25T12:00:01',
}

const ACTION = {
  id: 3,
  model_name: 'echo',
  model_version: null,
  input_snapshot: { ticket_id: 7 },
  confidence: 0.5,
  basis_refs: ['ticket:7'],
  trace_id: 'tr-2',
  actor: 1,
  decision: 'adopted' as const,
  created_at: 't',
}

describe('ai API (P4)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists ops events with filters (Page envelope)', async () => {
    const page = { list: [EVENT], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listEvents({ source: 'exec', entity_type: 'host', trace_id: 'tr-1', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/events', {
      params: { source: 'exec', entity_type: 'host', trace_id: 'tr-1', page: 1, size: 10 },
    })
    expect(result.list[0].entity_id).toBe('10.0.0.1')
  })

  it('gets an ops event detail (GET /events/{id})', async () => {
    vi.mocked(http.get).mockResolvedValue(ok(EVENT))
    const result = await getEvent(11)
    expect(http.get).toHaveBeenCalledWith('/events/11')
    expect(result.source).toBe('exec')
  })

  it('posts ticket suggest with empty body when no context', async () => {
    vi.mocked(http.post).mockResolvedValue(
      ok({ ticket_id: 7, suggestion: 's', model_name: 'echo', trace_id: 'tr', authoritative: false }),
    )
    const result = await ticketSuggest(7)
    expect(http.post).toHaveBeenCalledWith('/tickets/7/ai/suggest', {})
    expect(result.authoritative).toBe(false)
  })

  it('posts ticket suggest with context', async () => {
    vi.mocked(http.post).mockResolvedValue(
      ok({ ticket_id: 7, suggestion: 's', model_name: 'echo', trace_id: 'tr', authoritative: false }),
    )
    await ticketSuggest(7, '磁盘告警')
    expect(http.post).toHaveBeenCalledWith('/tickets/7/ai/suggest', { context: '磁盘告警' })
  })

  it('gets similar tickets with limit', async () => {
    vi.mocked(http.get).mockResolvedValue(ok({ ticket_id: 7, list: [], total: 0 }))
    await ticketSimilar(7, 3)
    expect(http.get).toHaveBeenCalledWith('/tickets/7/ai/similar', { params: { limit: 3 } })
  })

  it('posts semantic search (POST /kb/search/semantic)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ list: [], total: 0, mode: 'hybrid' }))
    await kbSearchSemantic({ q: 'cpu', mode: 'hybrid', limit: 10, entity_type: 'kb' })
    expect(http.post).toHaveBeenCalledWith('/kb/search/semantic', {
      q: 'cpu',
      mode: 'hybrid',
      limit: 10,
      entity_type: 'kb',
    })
  })

  it('posts kb answer (POST /kb/ai/answer)', async () => {
    vi.mocked(http.post).mockResolvedValue(
      ok({ answer: 'a', citations: [], model_name: 'echo', authoritative: false }),
    )
    const result = await kbAnswer({ q: 'cpu' })
    expect(http.post).toHaveBeenCalledWith('/kb/ai/answer', { q: 'cpu' })
    expect(result.answer).toBe('a')
  })

  it('posts feedback (POST /ai/feedback)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(ACTION))
    const result = await aiFeedback({ trace_id: 'tr-2', decision: 'adopted' })
    expect(http.post).toHaveBeenCalledWith('/ai/feedback', { trace_id: 'tr-2', decision: 'adopted' })
    expect(result.decision).toBe('adopted')
  })

  it('lists ai actions (GET /ai/actions, ai:admin surface)', async () => {
    vi.mocked(http.get).mockResolvedValue(ok({ list: [ACTION], total: 1, page: 1, size: 10 }))
    const result = await listAiActions({ decision: 'adopted', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/ai/actions', { params: { decision: 'adopted', page: 1, size: 10 } })
    expect(result.total).toBe(1)
  })
})
