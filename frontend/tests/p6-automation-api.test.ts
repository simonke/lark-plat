import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getAutomationLevel,
  setAutomationLevel,
  listAutomationWhitelist,
  createAutomationWhitelist,
  updateAutomationWhitelist,
  deleteAutomationWhitelist,
  automationDryRun,
  rollbackAutomationRun,
  getCircuitBreaker,
} from '../src/api/automation'
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

const LEVEL = {
  current: 'L3',
  matrix: [
    { level: 'L0', capability: '只读', enabled: false },
    { level: 'L3', capability: '人工确认', enabled: true },
    { level: 'L4', capability: '白名单低风险自动', enabled: false },
  ],
}

const ITEM = {
  id: 1,
  action: 'restart_service',
  risk_level: 'low' as const,
  enabled: true,
  updated_by: 1,
  updated_at: 't',
}

const DRY = {
  idempotency_key: 'dry-x-1',
  writable: false as const,
  items: [{ target: 'host#1', params: {}, expected_effect: 'dry-run of restart', risk_level: 'low' as const }],
}

const CB = { state: 'closed' as const, threshold: 3, current: 0, last_tripped_at: null }
const ROLLBACK = { status: 'rolled_back' as const, reason: null, window_expires_at: null }

describe('automation API (P6 E6)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('gets the level matrix (GET /ai/automation/level)', async () => {
    vi.mocked(http.get).mockResolvedValue(ok(LEVEL))
    const res = await getAutomationLevel()
    expect(http.get).toHaveBeenCalledWith('/ai/automation/level')
    expect(res.current).toBe('L3')
    expect(res.matrix).toHaveLength(3)
  })

  it('sets the level with { current } (PUT /ai/automation/level, ai:admin)', async () => {
    vi.mocked(http.put).mockResolvedValue(ok({ ...LEVEL, current: 'L4' }))
    const res = await setAutomationLevel('L4')
    expect(http.put).toHaveBeenCalledWith('/ai/automation/level', { current: 'L4' })
    expect(res.current).toBe('L4')
  })

  it('lists the whitelist with filters (GET /ai/automation/whitelist)', async () => {
    vi.mocked(http.get).mockResolvedValue(ok({ list: [ITEM], total: 1, page: 1, size: 10 }))
    const res = await listAutomationWhitelist({ action: 'restart_service', enabled: true, page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/ai/automation/whitelist', {
      params: { action: 'restart_service', enabled: true, page: 1, size: 10 },
    })
    expect(res.total).toBe(1)
  })

  it('creates a whitelist entry (POST /ai/automation/whitelist)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(ITEM))
    const res = await createAutomationWhitelist({ action: 'restart_service', risk_level: 'low', enabled: true })
    expect(http.post).toHaveBeenCalledWith('/ai/automation/whitelist', {
      action: 'restart_service',
      risk_level: 'low',
      enabled: true,
    })
    expect(res.risk_level).toBe('low')
  })

  it('updates a whitelist entry (PUT /ai/automation/whitelist/{id})', async () => {
    vi.mocked(http.put).mockResolvedValue(ok({ ...ITEM, enabled: false }))
    const res = await updateAutomationWhitelist(1, { enabled: false })
    expect(http.put).toHaveBeenCalledWith('/ai/automation/whitelist/1', { enabled: false })
    expect(res.enabled).toBe(false)
  })

  it('deletes a whitelist entry (DELETE /ai/automation/whitelist/{id})', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok({ id: 1, deleted: true }))
    const res = await deleteAutomationWhitelist(1)
    expect(http.delete).toHaveBeenCalledWith('/ai/automation/whitelist/1')
    expect(res.deleted).toBe(true)
  })

  it('posts a dry-run (POST /ai/automation/dry-run, ai:use)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(DRY))
    const res = await automationDryRun({ idempotency_key: 'dry-x-1', action: 'restart', target: 'host#1' })
    expect(http.post).toHaveBeenCalledWith('/ai/automation/dry-run', {
      idempotency_key: 'dry-x-1',
      action: 'restart',
      target: 'host#1',
    })
    expect(res.writable).toBe(false)
    expect(res.items[0].expected_effect).toContain('dry-run')
  })

  it('rolls back a run with an empty body (POST /runs/{run_id}/rollback, ai:admin)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(ROLLBACK))
    const res = await rollbackAutomationRun(42)
    expect(http.post).toHaveBeenCalledWith('/ai/automation/runs/42/rollback', {})
    expect(res.status).toBe('rolled_back')
  })

  it('gets the circuit breaker (GET /ai/automation/circuit-breaker, ai:use)', async () => {
    vi.mocked(http.get).mockResolvedValue(ok(CB))
    const res = await getCircuitBreaker()
    expect(http.get).toHaveBeenCalledWith('/ai/automation/circuit-breaker')
    expect(res.state).toBe('closed')
  })
})
