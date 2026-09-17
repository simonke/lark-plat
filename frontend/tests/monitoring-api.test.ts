import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getMetrics,
  getCurrentMetrics,
  listAlerts,
  getAlertEvent,
  resolveAlert,
  listAlertRules,
  createAlertRule,
  updateAlertRule,
  setRuleStatus,
  deleteAlertRule,
  getAdapters,
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

  it('should get metrics (object body with points), passing supported params only', async () => {
    const body = { agg: null, points: [{ ts: '2026-09-09T00:00:00Z', entity_id: 'h1', value: 50, source: 'agent' }], total: 1, page: 1, size: 500 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: body } })

    const result = await getMetrics({ metric_name: 'cpu_usage_percent', size: 500 })

    expect(http.get).toHaveBeenCalledWith('/monitor/metrics', {
      params: { metric_name: 'cpu_usage_percent', size: 500 },
    })
    expect(result).toEqual(body)
  })

  it('should get current metrics from the {list} envelope', async () => {
    const list = [{ entity_id: 'h1', metric_name: 'cpu', value: 50, ts: '2026-09-09T00:00:00Z' }]
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { list } } })

    const result = await getCurrentMetrics({ metric_name: 'cpu' })

    expect(http.get).toHaveBeenCalledWith('/monitor/metrics/current', { params: { metric_name: 'cpu' } })
    expect(result).toEqual(list)
  })

  it('should list alerts via /monitor/alerts with supported filters', async () => {
    const page = { list: [{ id: 7, status: 'firing', severity: 'critical', source: 'agent', entity: { entity_type: 'host', entity_id: 'h1', entity_name: 'h1' }, ts: '2026-09-09T00:00:00Z' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: page } })

    const result = await listAlerts({ status: 'firing', severity: 'critical' })

    expect(http.get).toHaveBeenCalledWith('/monitor/alerts', { params: { status: 'firing', severity: 'critical' } })
    expect(result).toEqual(page)
  })

  it('should get a single alert and resolve it with a body', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { id: 7 } } })
    const detail = await getAlertEvent(7)
    expect(http.get).toHaveBeenCalledWith('/monitor/alerts/7')
    expect(detail).toEqual({ id: 7 })

    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await resolveAlert(7)
    expect(http.post).toHaveBeenCalledWith('/monitor/alerts/7/resolve', { remark: '' })
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
      event_kind: 'metric' as const,
      condition_operator: '>' as const,
      condition_threshold: 90,
      scope_type: 'host',
      scope_ids: ['h1'],
      level: 'warning',
      cooldown_seconds: 300,
      converge_sec: 0,
      escalation_enabled: true,
      escalation_after_seconds: 600,
      escalation_severity: 'warning' as const,
      escalate_levels: ['warning', 'critical'],
      notify_scene: 'alert',
    }
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: { id: 1 } } })

    const result = await createAlertRule(payload)

    expect(http.post).toHaveBeenCalledWith('/monitor/rules', payload)
    expect(result).toEqual({ id: 1 })
  })

  it('should update and delete an alert rule', async () => {
    vi.mocked(http.put).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await updateAlertRule(1, { name: 'renamed' })
    expect(http.put).toHaveBeenCalledWith('/monitor/rules/1', { name: 'renamed' })

    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await setRuleStatus(1, false)
    expect(http.post).toHaveBeenCalledWith('/monitor/rules/1/status', { enabled: 0 })
    await setRuleStatus(1, true)
    expect(http.post).toHaveBeenCalledWith('/monitor/rules/1/status', { enabled: 1 })

    vi.mocked(http.delete).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await deleteAlertRule(1)
    expect(http.delete).toHaveBeenCalledWith('/monitor/rules/1')
  })

  it('should list adapters as a page and test by numeric id', async () => {
    const page = { list: [{ id: 5, type: 'prometheus', enabled: 1, status: 'healthy' }], total: 1, page: 1, size: 100 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: page } })
    const result = await getAdapters({ page: 1, size: 100 })
    expect(http.get).toHaveBeenCalledWith('/monitor/adapters', { params: { page: 1, size: 100 } })
    expect(result).toEqual(page)

    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: { ok: true, latency_ms: null, error_message: null } } })
    const test = await testAdapter(5)
    expect(http.post).toHaveBeenCalledWith('/monitor/adapters/5/test')
    expect(test.ok).toBe(true)
  })

  it('should fetch monitoring ws token', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { token: 'jwt' } } })
    const token = await getMonitoringWsToken()
    expect(http.get).toHaveBeenCalledWith('/monitor/ws-token')
    expect(token).toBe('jwt')
  })
})
