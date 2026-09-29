import { describe, it, expect } from 'vitest'
import { isFeatureDisabled } from '../src/api/featureGate'

function axiosLike(status: number, data: unknown) {
  return { isAxiosError: true, response: { status, data } }
}

describe('isFeatureDisabled (acceptance §G2 exact predicate)', () => {
  it('true only for HTTP 400 + body.code 400 + message "feature disabled"', () => {
    expect(isFeatureDisabled(axiosLike(400, { code: 400, message: 'feature disabled', data: null }))).toBe(true)
  })

  it('false for 403 permission denied (§G2b: never fold 403 into 未启用)', () => {
    expect(
      isFeatureDisabled(axiosLike(403, { code: 403, message: 'permission denied: system:user:list', data: null })),
    ).toBe(false)
    expect(isFeatureDisabled(axiosLike(403, { code: 403, message: 'forbidden', data: null }))).toBe(false)
  })

  it('false for a 400 with a different message (e.g. validation)', () => {
    expect(
      isFeatureDisabled(axiosLike(400, { code: 400, message: 'parameter validation failed', data: [] })),
    ).toBe(false)
  })

  it('false for other statuses', () => {
    expect(isFeatureDisabled(axiosLike(401, { code: 401, message: 'unauthorized', data: null }))).toBe(false)
    expect(isFeatureDisabled(axiosLike(500, { code: 500, message: 'feature disabled', data: null }))).toBe(false)
  })

  it('false for non-axios errors and missing response/body', () => {
    expect(isFeatureDisabled(new Error('network down'))).toBe(false)
    expect(isFeatureDisabled(undefined)).toBe(false)
    expect(isFeatureDisabled(null)).toBe(false)
    expect(isFeatureDisabled(axiosLike(400, undefined))).toBe(false)
  })
})
