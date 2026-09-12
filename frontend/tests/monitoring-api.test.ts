import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getMetrics,
  getCurrentMetrics,
  listAlertEvents,
  getAlertEvent,
  resolveAlert,
  listAlertRules,
  createAlertRule,
  updateAlertRule,
  setRuleStatus,
  deleteAlertRule,
  listAdapterStatus,
  testAdapter,
  getMonitoringWsToken,
} from '../src/api/monitoring'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('Monitoring API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should get metrics with agg query param', async () => {
    const series = [{ metric_name: 'cpu', entity_id: 'h1', entity_name: 'h1', source: 'agent', points: [{ ts: '2026-09-09T00:00:00Z', value: 50 }] }]
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: series } })

    const result = await getMetrics({ metric_name: 'cpu_usage_percent', agg: '5m' })

    expect(http.get).toHaveBeenCalledWith('/monitor/metrics', { params: { metric_name: 'cpu_usage_percent', agg: '5m' } })
    expect(result).toEqual(series)
  })

  it('should get current metrics snapshot', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: [] } })

    await getCurrentMetrics({ metric_name: 'cpu' })

    expect(http.get).toHaveBeenCalledWith('/monitor/metrics/current', { params: { metric_name: 'cpu' } })
  })

  it('should list alert events', async () => {
    const page = { list: [{ id: 'a1' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: page } })

    const result = await listAlertEvents({ status: 'firing' })

    expect(http.get).toHaveBeenCalledWith('/monitor/alerts', { params: { status: 'firing' } })
    expect(result).toEqual(page)
  })

  it('should get single alert and resolve it', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { id: 'a1' } } })
    const detail = await getAlertEvent('a1')
    expect(http.get).toHaveBeenCalledWith('/monitor/alerts/a1')
    expect(detail).toEqual({ id: 'a1' })

    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await resolveAlert('a1')
    expect(http.post).toHaveBeenCalledWith('/monitor/alerts/a1/resolve')
  })

  it('should list alert rules', async () => {
    const page = { list: [], total: 0, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: page } })

    const result = await listAlertRules({ page: 1, size: 10 })

    expect(http.get).toHaveBeenCalledWith('/monitor/rules', { params: { page: 1, size: 10 } })
    expect(result).toEqual(page)
  })

  it('should create an alert rule', async () => {
    const payload = {
      name: 'high-cpu',
      event_kind: 'metric',
      condition_operator: '>',
      condition_threshold: 90,
      scope_type: 'host',
      scope_ids: ['h1'],
      level: 'warning',
      cooldown_seconds: 300,
      converge_sec: 0,
      escalation_enabled: true,
      escalation_after_seconds: 600,
      escalation_severity: 'warning',
      escalate_levels: ['warning', 'critical'],
      notify_scene: 'alert',
    }
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: { id: 'r1' } } })

    const result = await createAlertRule(payload)

    expect(http.post).toHaveBeenCalledWith('/monitor/rules', payload)
    expect(result).toEqual({ id: 'r1' })
  })

  it('should update and delete an alert rule', async () => {
    vi.mocked(http.put).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await updateAlertRule('r1', { name: 'renamed' })
    expect(http.put).toHaveBeenCalledWith('/monitor/rules/r1', { name: 'renamed' })

    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await setRuleStatus('r1', false)
    expect(http.post).toHaveBeenCalledWith('/monitor/rules/r1/status', { enabled: 0 })
    await setRuleStatus('r1', true)
    expect(http.post).toHaveBeenCalledWith('/monitor/rules/r1/status', { enabled: 1 })

    vi.mocked(http.delete).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await deleteAlertRule('r1')
    expect(http.delete).toHaveBeenCalledWith('/monitor/rules/r1')
  })

  it('should list adapter status and test an adapter', async () => {
    const adapters = [{ type: 'prometheus', enabled: true, connected: true }]
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: adapters } })
    const status = await listAdapterStatus()
    expect(http.get).toHaveBeenCalledWith('/monitor/adapters')
    expect(status).toEqual(adapters)

    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: { ok: true, detail: 'ok' } } })
    const result = await testAdapter('prometheus')
    expect(http.post).toHaveBeenCalledWith('/monitor/adapters/prometheus/test')
    expect(result.ok).toBe(true)
  })

  it('should fetch monitoring ws token', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { token: 'jwt' } } })
    const token = await getMonitoringWsToken()
    expect(http.get).toHaveBeenCalledWith('/monitor/ws-token')
    expect(token).toBe('jwt')
  })
})
