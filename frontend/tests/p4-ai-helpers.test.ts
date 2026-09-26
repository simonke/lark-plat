import { describe, it, expect } from 'vitest'
import {
  OPS_EVENT_SOURCES,
  AI_ACTION_DECISIONS,
  sourceLabel,
  sourceTag,
  decisionLabel,
  decisionTag,
  branchLabel,
  confidencePercent,
  eventSummary,
  shortTrace,
  articleIdFromDocRef,
} from '../src/views/ai/helpers'

describe('ai helpers (P4)', () => {
  it('freezes the source / decision vocabularies (P6 add-only: + dry_run)', () => {
    expect(OPS_EVENT_SOURCES).toEqual(['monitor', 'exec', 'audit', 'ticket', 'kb'])
    expect(AI_ACTION_DECISIONS).toEqual(['adopted', 'rejected', 'auto', 'dry_run'])
  })

  it('maps source + decision labels', () => {
    expect(sourceLabel('monitor')).toBe('监控')
    expect(sourceLabel('unknown')).toBe('unknown')
    expect(decisionLabel('adopted')).toBe('已采纳')
    expect(decisionLabel('auto')).toBe('自动记录')
  })

  it('maps tags', () => {
    expect(sourceTag('monitor')).toBe('danger')
    expect(sourceTag('kb')).toBe('success')
    expect(decisionTag('adopted')).toBe('success')
    expect(decisionTag('rejected')).toBe('danger')
  })

  it('maps retrieval branch labels', () => {
    expect(branchLabel('vector')).toBe('向量')
    expect(branchLabel('hybrid')).toBe('混合')
  })

  it('formats confidence as a percentage with null guard', () => {
    expect(confidencePercent(0.87)).toBe('87%')
    expect(confidencePercent(null)).toBe('-')
    expect(confidencePercent(undefined)).toBe('-')
  })

  it('summarises an event and truncates long traces', () => {
    expect(eventSummary({ entity_type: 'host', entity_id: '10.0.0.1', action: 'restart' })).toBe(
      'host#10.0.0.1 · restart',
    )
    expect(shortTrace(null)).toBe('-')
    expect(shortTrace('short')).toBe('short')
    expect(shortTrace('x'.repeat(40))).toHaveLength(22)
  })

  it('maps only numeric doc_refs to navigable article ids', () => {
    expect(articleIdFromDocRef('42')).toBe(42)
    expect(articleIdFromDocRef(' 7 ')).toBe(7)
    expect(articleIdFromDocRef('doc-abc')).toBeNull()
    expect(articleIdFromDocRef('0')).toBeNull()
    expect(articleIdFromDocRef('')).toBeNull()
    expect(articleIdFromDocRef(null)).toBeNull()
    expect(articleIdFromDocRef(undefined)).toBeNull()
  })
})
