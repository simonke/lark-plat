import { describe, it, expect, beforeEach } from 'vitest'
import { getTokens, setTokens, clearTokens, hasToken } from '../src/api/tokens'

describe('tokens', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('getTokens returns empty strings when nothing stored', () => {
    const tokens = getTokens()
    expect(tokens.access_token).toBe('')
    expect(tokens.refresh_token).toBe('')
  })

  it('setTokens persists both tokens to localStorage', () => {
    setTokens('access-1', 'refresh-1')
    expect(localStorage.getItem('lark_access_token')).toBe('access-1')
    expect(localStorage.getItem('lark_refresh_token')).toBe('refresh-1')
    expect(getTokens()).toEqual({ access_token: 'access-1', refresh_token: 'refresh-1' })
  })

  it('clearTokens removes both tokens', () => {
    setTokens('access-1', 'refresh-1')
    clearTokens()
    expect(localStorage.getItem('lark_access_token')).toBeNull()
    expect(localStorage.getItem('lark_refresh_token')).toBeNull()
    expect(getTokens()).toEqual({ access_token: '', refresh_token: '' })
  })

  it('hasToken is true only when access token present', () => {
    expect(hasToken()).toBe(false)
    setTokens('access-1', 'refresh-1')
    expect(hasToken()).toBe(true)
    clearTokens()
    expect(hasToken()).toBe(false)
  })

  it('hasToken returns false when only refresh token present', () => {
    localStorage.setItem('lark_refresh_token', 'refresh-1')
    expect(hasToken()).toBe(false)
  })
})
