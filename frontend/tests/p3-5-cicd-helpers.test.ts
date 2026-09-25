import { describe, it, expect } from 'vitest'
import {
  canCancel,
  canCanary,
  canDeploy,
  canFail,
  canPromote,
  canRollback,
  envLabel,
  isTerminal,
  releaseStatusLabel,
  releaseStatusTag,
} from '../src/views/releases/helpers'
import { providerStatusTag, providerTypeLabel } from '../src/views/cicd/helpers'

describe('release helpers (P3-5)', () => {
  it('maps release status tags', () => {
    expect(releaseStatusTag('succeeded')).toBe('success')
    expect(releaseStatusTag('failed')).toBe('danger')
    expect(releaseStatusTag('rolled_back')).toBe('warning')
    expect(releaseStatusTag('cancelled')).toBe('info')
    expect(releaseStatusTag('deploying')).toBe('primary')
    expect(releaseStatusTag('canary')).toBe('primary')
  })

  it('labels release status and env', () => {
    expect(releaseStatusLabel('pending')).toBe('待发布')
    expect(releaseStatusLabel('canary')).toBe('灰度中')
    expect(envLabel('prod')).toBe('生产')
    expect(envLabel('zzz')).toBe('zzz')
  })

  it('cancels only from pending|deploying|canary (§14.1)', () => {
    expect(canCancel('pending')).toBe(true)
    expect(canCancel('deploying')).toBe(true)
    expect(canCancel('canary')).toBe(true)
    expect(canCancel('succeeded')).toBe(false)
    expect(canCancel('cancelled')).toBe(false)
  })

  it('terminal set covers exception + terminal statuses', () => {
    expect(isTerminal('succeeded')).toBe(true)
    expect(isTerminal('failed')).toBe(true)
    expect(isTerminal('rolled_back')).toBe(true)
    expect(isTerminal('cancelled')).toBe(true)
    expect(isTerminal('canary')).toBe(false)
  })

  it('gates canary/promote/rollback by allowed source set (@架构 seq3077)', () => {
    expect(canCanary('pending')).toBe(true)
    expect(canCanary('deploying')).toBe(true)
    expect(canCanary('canary')).toBe(false)
    expect(canPromote('canary')).toBe(true)
    expect(canPromote('deploying')).toBe(false)
    expect(canPromote('pending')).toBe(false)
    expect(canRollback('deploying')).toBe(true)
    expect(canRollback('canary')).toBe(true)
    expect(canRollback('failed')).toBe(true)
    expect(canRollback('succeeded')).toBe(false)
    expect(canRollback('pending')).toBe(false)
  })

  it('gates deploy/fail by allowed source set (P3-6 tuple v1 seq3127)', () => {
    expect(canDeploy('pending')).toBe(true)
    expect(canDeploy('deploying')).toBe(false)
    expect(canDeploy('canary')).toBe(false)
    expect(canFail('deploying')).toBe(true)
    expect(canFail('canary')).toBe(true)
    expect(canFail('pending')).toBe(false)
    expect(canFail('failed')).toBe(false)
    expect(canFail('succeeded')).toBe(false)
  })
})

describe('cicd provider helpers (P3-5)', () => {
  it('labels provider types', () => {
    expect(providerTypeLabel('gitlab')).toBe('GitLab')
    expect(providerTypeLabel('jenkins')).toBe('Jenkins')
    expect(providerTypeLabel('generic')).toBe('通用 Webhook')
    expect(providerTypeLabel('x')).toBe('x')
  })

  it('maps provider status tags', () => {
    expect(providerStatusTag('ok')).toBe('success')
    expect(providerStatusTag('online')).toBe('success')
    expect(providerStatusTag('offline')).toBe('danger')
    expect(providerStatusTag('unknown')).toBe('info')
  })
})
