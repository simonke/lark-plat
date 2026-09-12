/**
 * Monitoring API �?new file frontend/src/api/monitoring.ts (P2-MA v3.0)
 * Contract: api-design-v3.md §2 P2-MA 资源命名 (/monitor/*, WS /ws/monitor).
 */
import http from './http'
import type {
  Result,
  Page,
  MonMetricSeries,
  MonMetricQuery,
  MonAlertEventOut,
  MonAlertEventQuery,
  AlertRuleCreate,
  AlertRuleUpdate,
  AlertRuleOut,
  AlertRuleQuery,
  AdapterStatus,
  AdapterTestResult,
} from './types'

export async function getMetrics(params?: MonMetricQuery): Promise<MonMetricSeries[]> {
  const { data } = await http.get<Result<MonMetricSeries[]>>('/monitor/metrics', { params })
  return data.data
}

export async function getCurrentMetrics(params?: MonMetricQuery): Promise<MonMetricSeries[]> {
  const { data } = await http.get<Result<MonMetricSeries[]>>('/monitor/metrics/current', { params })
  return data.data
}

export async function listAlertEvents(params?: MonAlertEventQuery): Promise<Page<MonAlertEventOut>> {
  const { data } = await http.get<Result<Page<MonAlertEventOut>>>('/monitor/alerts', { params })
  return data.data
}

export async function getAlertEvent(id: string): Promise<MonAlertEventOut> {
  const { data } = await http.get<Result<MonAlertEventOut>>(`/monitor/alerts/${id}`)
  return data.data
}

export async function resolveAlert(id: string): Promise<void> {
  await http.post<Result<void>>(`/monitor/alerts/${id}/resolve`)
}

export async function listAlertRules(params?: AlertRuleQuery): Promise<Page<AlertRuleOut>> {
  const { data } = await http.get<Result<Page<AlertRuleOut>>>('/monitor/rules', { params })
  return data.data
}

export async function createAlertRule(payload: AlertRuleCreate): Promise<AlertRuleOut> {
  const { data } = await http.post<Result<AlertRuleOut>>('/monitor/rules', payload)
  return data.data
}

export async function updateAlertRule(id: string, payload: AlertRuleUpdate): Promise<void> {
  await http.put<Result<void>>(`/monitor/rules/${id}`, payload)
}

export async function setRuleStatus(id: string, enabled: boolean): Promise<void> {
  await http.post<Result<void>>(`/monitor/rules/${id}/status`, { enabled: enabled ? 1 : 0 })
}

export async function deleteAlertRule(id: string): Promise<void> {
  await http.delete<Result<void>>(`/monitor/rules/${id}`)
}

export async function listAdapterStatus(): Promise<AdapterStatus[]> {
  const { data } = await http.get<Result<AdapterStatus[]>>('/monitor/adapters')
  return data.data
}

export async function testAdapter(type: string): Promise<AdapterTestResult> {
  const { data } = await http.post<Result<AdapterTestResult>>(`/monitor/adapters/${type}/test`)
  return data.data
}

export async function getMonitoringWsToken(): Promise<string> {
  const { data } = await http.get<Result<{ token: string }>>('/monitor/ws-token')
  return data.data.token
}
