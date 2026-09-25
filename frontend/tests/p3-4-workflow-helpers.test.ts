import { describe, it, expect } from 'vitest'
import { parseDefinition, callbackOutput, formatDefinition, runStatusTag, kindLabel, kindTag } from '../src/views/workflow/helpers'

describe('workflow helpers (P3-4)', () => {
  it('parseDefinition accepts {"nodes":[]}', () => {
    expect(parseDefinition('{"nodes":[]}')).toEqual({ nodes: [] })
  })

  it('parseDefinition rejects non-JSON', () => {
    expect(() => parseDefinition('not json')).toThrow()
  })

  it('parseDefinition rejects an object without nodes[]', () => {
    expect(() => parseDefinition('{"a":1}')).toThrow()
  })

  it('formatDefinition renders a stable JSON skeleton for null', () => {
    expect(JSON.parse(formatDefinition(null))).toEqual({ nodes: [] })
  })

  it('callbackOutput extracts {token,url,expires_at} from node output', () => {
    const out = callbackOutput({
      callback: { token: 't', url: 'https://x/cb', expires_at: '2026-01-01T00:00:00' },
    })
    expect(out?.url).toBe('https://x/cb')
    expect(out?.token).toBe('t')
  })

  it('callbackOutput returns null when absent', () => {
    expect(callbackOutput(null)).toBeNull()
    expect(callbackOutput({})).toBeNull()
  })

  it('runStatusTag maps terminal statuses', () => {
    expect(runStatusTag('succeeded')).toBe('success')
    expect(runStatusTag('failed')).toBe('danger')
    expect(runStatusTag('cancelled')).toBe('info')
  })

  it('kindLabel/kindTag discriminate playbook vs workflow (P5)', () => {
    expect(kindLabel('playbook')).toBe('预案')
    expect(kindLabel('workflow')).toBe('编排')
    expect(kindLabel(undefined)).toBe('编排')
    expect(kindTag('playbook')).toBe('warning')
    expect(kindTag('workflow')).toBe('primary')
  })
})
