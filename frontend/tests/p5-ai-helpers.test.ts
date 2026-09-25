import { describe, it, expect } from 'vitest'
import {
  RCA_DEPTH_MIN,
  RCA_DEPTH_MAX,
  RCA_DEPTH_DEFAULT,
  PLAYBOOK_KINDS,
  normalizeRcaDepth,
  severityLabel,
  severityTag,
  rootEntityLabel,
} from '../src/views/ai/helpers'

describe('ai helpers (P5 E4/E5)', () => {
  it('freezes the RCA depth domain (mirrors cmdb_service 0..3, default 2)', () => {
    expect(RCA_DEPTH_MIN).toBe(0)
    expect(RCA_DEPTH_MAX).toBe(3)
    expect(RCA_DEPTH_DEFAULT).toBe(2)
  })

  it('freezes the playbook kinds (reuse the workflow engine)', () => {
    expect(PLAYBOOK_KINDS).toEqual(['workflow', 'playbook'])
  })

  it('normalises depth: 0..3 kept (0 legal), out-of-range/null -> default 2', () => {
    expect(normalizeRcaDepth(0)).toBe(0)
    expect(normalizeRcaDepth(1)).toBe(1)
    expect(normalizeRcaDepth(3)).toBe(3)
    expect(normalizeRcaDepth(-1)).toBe(2)
    expect(normalizeRcaDepth(4)).toBe(2)
    expect(normalizeRcaDepth(null)).toBe(2)
    expect(normalizeRcaDepth(undefined)).toBe(2)
    expect(normalizeRcaDepth(2.5)).toBe(2)
  })

  it('maps severity labels and tags', () => {
    expect(severityLabel('critical')).toBe('严重')
    expect(severityLabel(null)).toBe('-')
    expect(severityTag('critical')).toBe('danger')
    expect(severityTag('warning')).toBe('warning')
    expect(severityTag('info')).toBe('info')
    expect(severityTag('unknown')).toBe('info')
  })

  it('labels the root entity with a name/id preference', () => {
    expect(rootEntityLabel({ type: 'host', id: '10.0.0.1', name: 'web-1' })).toBe('host#web-1')
    expect(rootEntityLabel({ type: 'host', id: '10.0.0.1', name: null })).toBe('host#10.0.0.1')
    expect(rootEntityLabel(null)).toBe('-')
  })
})
