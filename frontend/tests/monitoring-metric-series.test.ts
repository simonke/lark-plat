import { describe, it, expect } from 'vitest'
import { buildMetricSeries } from '../src/views/monitoring/metricSeries'
import type { MonMetricResult } from '../src/api/types'

describe('buildMetricSeries', () => {
  it('reads the contract-frozen {ts,value} agg point', () => {
    const res = {
      agg: '5m',
      points: [
        { ts: '2026-09-09T00:00:00Z', value: 12.5 },
        { ts: '2026-09-09T00:05:00Z', value: 13 },
      ],
      total: 2,
      page: 1,
      size: 500,
    } as unknown as MonMetricResult

    expect(buildMetricSeries(res, 'cpu')).toEqual([
      { name: 'cpu (5m avg)', data: [['2026-09-09T00:00:00Z', 12.5], ['2026-09-09T00:05:00Z', 13]] },
    ])
  })

  it('still tolerates the legacy {bucket,avg} agg shape', () => {
    const res = {
      agg: '1h',
      points: [{ bucket: '2026-09-09T00:00:00Z', avg: 7, max: 9, min: 1, count: 4 }],
    } as unknown as MonMetricResult

    expect(buildMetricSeries(res, 'mem')).toEqual([
      { name: 'mem (1h avg)', data: [['2026-09-09T00:00:00Z', 7]] },
    ])
  })

  it('splits multi-entity agg points by entity_id', () => {
    const res = {
      agg: '5m',
      points: [
        { ts: '2026-09-09T00:00:00Z', value: 1, entity_id: 'h1' },
        { ts: '2026-09-09T00:00:00Z', value: 2, entity_id: 'h2' },
      ],
    } as unknown as MonMetricResult

    expect(buildMetricSeries(res, 'cpu')).toEqual([
      { name: 'cpu (5m avg) · h1', data: [['2026-09-09T00:00:00Z', 1]] },
      { name: 'cpu (5m avg) · h2', data: [['2026-09-09T00:00:00Z', 2]] },
    ])
  })

  it('groups raw sample points by entity', () => {
    const res = {
      agg: null,
      points: [
        { ts: '2026-09-09T00:00:00Z', entity_id: 'h1', value: 1, source: 'agent' },
        { ts: '2026-09-09T00:01:00Z', entity_id: 'h1', value: 2, source: 'agent' },
      ],
    } as unknown as MonMetricResult

    expect(buildMetricSeries(res, 'cpu')).toEqual([
      { name: 'h1', data: [['2026-09-09T00:00:00Z', 1], ['2026-09-09T00:01:00Z', 2]] },
    ])
  })

  it('returns empty for null or empty results', () => {
    expect(buildMetricSeries(null, 'cpu')).toEqual([])
    expect(buildMetricSeries({ agg: null, points: [] }, 'cpu')).toEqual([])
  })
})
