/**
 * Monitoring API — frontend/src/api/monitoring.ts (P2-MA v3.0)
 * Contract: api-design-v3.md §2 P2-MA 资源命名 (/monitor/*, WS /ws/monitor).
 * Shapes verified against live :8000 openapi + monitor_service (P2-MA 收口自检).
 */
import http from './http'
import type {
  Result,
  Page,
  MonMetricResult,
  MonMetricQuery,
  MonCurrentMetric,
  MonAlertOut,
  MonAlertQuery,
  AlertRuleCreate,
  AlertRuleUpdate,
  AlertRuleOut,
  AlertRuleQuery,
  MonAdapterOut,
  AdapterTestResult,
} from './types'

export async function getMetrics(params?: MonMetricQuery): Promise<MonMetricResult> {
  const { data } = await http.get<Result<MonMetricResult>>('/monitor/metrics', { params })
  return data.data
}

export async function getCurrentMetrics(params?: {
  entity_ids?: string
  metric_name?: string
}): Promise<MonCurrentMetric[]> {
  const { data } = await http.get<Result<{ list: MonCurrentMetric[] }>>('/monitor/metrics/current', {
    params,
  })
  return data.data.list
}

export async function listAlerts(params?: MonAlertQuery): Promise<Page<MonAlertOut>> {
  const { data } = await http.get<Result<Page<MonAlertOut>>>('/monitor/alerts', { params })
  return data.data
}

export async function getAlertEvent(id: number): Promise<MonAlertOut> {
  const { data } = await http.get<Result<MonAlertOut>>(`/monitor/alerts/${id}`)
  return data.data
}

export async function resolveAlert(id: number, remark = ''): Promise<void> {
  await http.post<Result<void>>(`/monitor/alerts/${id}/resolve`, { remark })
}

export async function listAlertRules(params?: AlertRuleQuery): Promise<Page<AlertRuleOut>> {
  const { data } = await http.get<Result<Page<AlertRuleOut>>>('/monitor/rules', { params })
  return data.data
}

export async function createAlertRule(payload: AlertRuleCreate): Promise<AlertRuleOut> {
  const { data } = await http.post<Result<AlertRuleOut>>('/monitor/rules', payload)
  return data.data
}

export async function updateAlertRule(id: number, payload: AlertRuleUpdate): Promise<void> {
  await http.put<Result<void>>(`/monitor/rules/${id}`, payload)
}

export async function setRuleStatus(id: number, enabled: boolean): Promise<void> {
  await http.post<Result<void>>(`/monitor/rules/${id}/status`, { enabled: enabled ? 1 : 0 })
}

export async function deleteAlertRule(id: number): Promise<void> {
  await http.delete<Result<void>>(`/monitor/rules/${id}`)
}

export async function getAdapters(params?: {
  enabled?: number
  type?: string
  page?: number
  size?: number
}): Promise<Page<MonAdapterOut>> {
  const { data } = await http.get<Result<Page<MonAdapterOut>>>('/monitor/adapters', { params })
  return data.data
}

export async function testAdapter(id: number): Promise<AdapterTestResult> {
  const { data } = await http.post<Result<AdapterTestResult>>(`/monitor/adapters/${id}/test`)
  return data.data
}

export async function getMonitoringWsToken(): Promise<string> {
  const { data } = await http.get<Result<{ token: string }>>('/monitor/ws-token')
  return data.data.token
}
