import type { MonMetricBucket, MonMetricResult, MonMetricSamplePoint } from '../../api/types'

export interface MetricSeries {
  name: string
  data: [string, number][]
}

// 契约 §2 冻结 agg 点为 {ts,value}（add-only 可附 bucket/avg/entity_id）。
// 兼容修复前旧形状 {bucket,avg}；多 entity 时按 entity_id 分组。
export function buildMetricSeries(res: MonMetricResult | null, metricName: string): MetricSeries[] {
  if (!res || res.points.length === 0) return []
  if (res.agg) {
    const pts = res.points as MonMetricBucket[]
    const name = `${metricName} (${res.agg} avg)`
    const byEntity = new Map<string, [string, number][]>()
    for (const p of pts) {
      const ts = p.ts ?? p.bucket ?? ''
      const value = p.value ?? p.avg
      if (value === undefined || value === null) continue
      const list = byEntity.get(p.entity_id ?? '') ?? []
      list.push([ts, value])
      byEntity.set(p.entity_id ?? '', list)
    }
    if (byEntity.size === 0) return []
    if (byEntity.size === 1) return [{ name, data: [...byEntity.values()][0] }]
    return [...byEntity.entries()].map(([eid, data]) => ({ name: `${name} · ${eid}`, data }))
  }
  const byEntity = new Map<string, [string, number][]>()
  for (const p of res.points as MonMetricSamplePoint[]) {
    const list = byEntity.get(p.entity_id) ?? []
    list.push([p.ts, p.value])
    byEntity.set(p.entity_id, list)
  }
  return [...byEntity.entries()].map(([eid, data]) => ({ name: eid, data }))
}
