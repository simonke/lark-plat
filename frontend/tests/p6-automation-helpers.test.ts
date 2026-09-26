import { describe, it, expect } from 'vitest'
import {
  AI_ACTION_DECISIONS,
  decisionLabel,
  AUTOMATION_LEVELS,
  AUTOMATION_MAX_LEVEL,
  AUTOMATION_DEFAULT_LEVEL,
  RISK_LEVELS,
  APPROVAL_MODES,
  L4_AUTO_RISK_LEVELS,
  riskLabel,
  riskTag,
  isAutoEligibleRisk,
  approvalModeLabel,
  approvalModeTag,
  circuitStateLabel,
  circuitStateTag,
  levelIndex,
  isLevelWithin,
  buildDryRunKey,
} from '../src/views/ai/helpers'

describe('ai helpers (P6 E6)', () => {
  it('adds dry_run to the frozen decision vocabulary (add-only)', () => {
    expect(AI_ACTION_DECISIONS).toEqual(['adopted', 'rejected', 'auto', 'dry_run'])
    expect(decisionLabel('dry_run')).toBe('预演')
  })

  it('freezes the level ladder L0..L4 with L4 as the max (no L5 self-healing)', () => {
    expect(AUTOMATION_LEVELS).toEqual(['L0', 'L1', 'L2', 'L3', 'L4'])
    expect(AUTOMATION_MAX_LEVEL).toBe('L4')
    expect(AUTOMATION_DEFAULT_LEVEL).toBe('L3')
  })

  it('mirrors the risk / approval vocabularies', () => {
    expect(RISK_LEVELS).toEqual(['low', 'medium', 'high'])
    expect(APPROVAL_MODES).toEqual(['auto_policy', 'manual'])
    expect(L4_AUTO_RISK_LEVELS).toEqual(['low'])
  })

  it('maps risk labels and tags', () => {
    expect(riskLabel('low')).toBe('低')
    expect(riskLabel(null)).toBe('-')
    expect(riskTag('low')).toBe('success')
    expect(riskTag('medium')).toBe('warning')
    expect(riskTag('high')).toBe('danger')
    expect(riskTag('n/a')).toBe('info')
  })

  it('only `low` is auto-eligible for L4', () => {
    expect(isAutoEligibleRisk('low')).toBe(true)
    expect(isAutoEligibleRisk('medium')).toBe(false)
    expect(isAutoEligibleRisk('high')).toBe(false)
    expect(isAutoEligibleRisk(null)).toBe(false)
  })

  it('labels approval modes (auto_policy vs manual)', () => {
    expect(approvalModeLabel('auto_policy')).toBe('策略自动批准')
    expect(approvalModeLabel('manual')).toBe('人工审批')
    expect(approvalModeLabel(null)).toBe('-')
    expect(approvalModeTag('auto_policy')).toBe('warning')
    expect(approvalModeTag('manual')).toBe('info')
  })

  it('labels circuit-breaker states', () => {
    expect(circuitStateLabel('closed')).toBe('正常')
    expect(circuitStateLabel('open')).toBe('熔断')
    expect(circuitStateTag('closed')).toBe('success')
    expect(circuitStateTag('half')).toBe('warning')
    expect(circuitStateTag('open')).toBe('danger')
  })

  it('maps the ladder and guards the max tier', () => {
    expect(levelIndex('L0')).toBe(0)
    expect(levelIndex('L4')).toBe(4)
    expect(levelIndex('L5')).toBe(-1)
    expect(isLevelWithin('L3')).toBe(true)
    expect(isLevelWithin('L4')).toBe(true)
    expect(isLevelWithin('L5')).toBe(false)
    expect(isLevelWithin('unknown')).toBe(false)
  })

  it('builds deterministic dry-run keys', () => {
    expect(buildDryRunKey('restart', 1)).toBe('dry-restart-1')
    expect(buildDryRunKey('', 2)).toBe('dry-noop-2')
    expect(buildDryRunKey(null, 3)).toBe('dry-noop-3')
  })
})
