import { describe, it, expect, vi, beforeEach } from 'vitest'
import { aggregateAlerts, alertRca, suggestPlaybook } from '../src/api/ai'
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

const AGG = {
  list: [{ entity_id: '10.0.0.1', entity_type: 'host', count: 3, max_severity: 'critical', alert_ids: [9, 8, 7] }],
  total: 1,
  page: 1,
  size: 10,
  generated_at: 't',
  authoritative: false,
}

const RCA = {
  alert_id: 9,
  root_entity: { type: 'host', id: '10.0.0.1', name: 'web-1' },
  depth: 2,
  candidates: [{ entity_type: 'host', entity_id: '10.0.0.2', score: 1, reason: 'downstream-of-alert-entity', evidence: [] }],
  generated_at: 't',
  authoritative: false,
}

const SUGGEST = {
  kind: 'playbook',
  supported_kinds: ['workflow', 'playbook'],
  goal: '恢复 Nginx',
  definition: { nodes: [] },
  model_name: 'echo',
  authoritative: false,
}

describe('ai API (P5 E4/E5)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('aggregates alerts with filters (GET /monitor/alerts/aggregate)', async () => {
    vi.mocked(http.get).mockResolvedValue(ok(AGG))
    const res = await aggregateAlerts({ status: 'firing', severity: 'critical', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/monitor/alerts/aggregate', {
      params: { status: 'firing', severity: 'critical', page: 1, size: 10 },
    })
    expect(res.list[0].count).toBe(3)
  })

  it('posts RCA with empty body when depth is omitted', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(RCA))
    const res = await alertRca(9)
    expect(http.post).toHaveBeenCalledWith('/monitor/alerts/9/ai/rca', {})
    expect(res.authoritative).toBe(false)
  })

  it('posts RCA with explicit depth', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(RCA))
    await alertRca(9, 0)
    expect(http.post).toHaveBeenCalledWith('/monitor/alerts/9/ai/rca', { depth: 0 })
  })

  it('posts playbook suggest (POST /workflows/ai/suggest)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(SUGGEST))
    const res = await suggestPlaybook({ goal: '恢复 Nginx', context: '5xx 告警' })
    expect(http.post).toHaveBeenCalledWith('/workflows/ai/suggest', {
      goal: '恢复 Nginx',
      context: '5xx 告警',
    })
    expect(res.kind).toBe('playbook')
    expect(res.supported_kinds).toContain('playbook')
  })
})
