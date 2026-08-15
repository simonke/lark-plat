import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import axios from 'axios'
import MockAdapter from 'axios-mock-adapter'
import { http, request, extractError } from '../src/api/http'
import { setTokens, clearTokens } from '../src/api/tokens'

const REFRESH_OK = {
  code: 0,
  message: 'ok',
  data: { access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer' },
}

function saveLocation(): void {
  const loc = window.location as unknown
  Object.defineProperty(window, 'location', {
    value: { ...(loc as Location), href: '', pathname: '/dashboard' },
    configurable: true,
    writable: true,
  })
}

function restoreLocation(): void {
  delete (window as { location?: unknown }).location
}

describe('http', () => {
  let mockHttp: MockAdapter
  let mockDefault: MockAdapter

  beforeEach(() => {
    localStorage.clear()
    clearTokens()
    mockHttp = new MockAdapter(http)
    mockDefault = new MockAdapter(axios)
    saveLocation()
  })

  afterEach(() => {
    mockHttp.restore()
    mockDefault.restore()
    restoreLocation()
  })

  it('injects Authorization header when access token present', async () => {
    setTokens('access-1', 'refresh-1')
    let seenAuth = ''
    mockHttp.onGet('/api/v1/system/users').reply((config) => {
      seenAuth = config.headers?.Authorization ?? ''
      return [200, { code: 0, message: 'ok', data: { list: [], total: 0, page: 1, size: 10 } }]
    })
    await http.get('/system/users')
    expect(seenAuth).toBe('Bearer access-1')
  })

  it('does not inject Authorization when no token', async () => {
    let seenAuth: string | undefined = 'unset'
    mockHttp.onGet('/api/v1/system/users').reply((config) => {
      seenAuth = config.headers?.Authorization as string | undefined
      return [200, { code: 0, message: 'ok', data: { list: [], total: 0, page: 1, size: 10 } }]
    })
    await http.get('/system/users')
    expect(seenAuth).toBeUndefined()
  })

  it('401 on protected path triggers refresh and retries with new token', async () => {
    setTokens('expired-access', 'refresh-1')
    mockDefault.onPost('/api/v1/auth/refresh').reply(200, REFRESH_OK)
    let first = true
    mockHttp.onGet('/api/v1/system/users').reply((config) => {
      if (first) {
        first = false
        return [401, { code: 401, message: 'unauthorized', data: null }]
      }
      expect(config.headers?.Authorization).toBe('Bearer new-access')
      return [200, { code: 0, message: 'ok', data: { list: [], total: 0, page: 1, size: 10 } }]
    })
    const resp = await http.get('/system/users')
    expect(resp.data.data.list).toEqual([])
    expect(localStorage.getItem('lark_access_token')).toBe('new-access')
    expect(localStorage.getItem('lark_refresh_token')).toBe('new-refresh')
  })

  it('login path is whitelisted and does not attempt refresh on 401', async () => {
    let refreshCalled = 0
    mockDefault.onPost('/api/v1/auth/refresh').reply(() => {
      refreshCalled += 1
      return [200, REFRESH_OK]
    })
    mockHttp.onPost('/api/v1/auth/login').reply(401, { code: 401, message: 'bad credentials', data: null })
    await expect(http.post('/auth/login', { username: 'u', password: 'p' })).rejects.toBeTruthy()
    expect(refreshCalled).toBe(0)
  })

  it('refresh failure clears tokens and redirects to login', async () => {
    setTokens('expired-access', 'expired-refresh')
    mockDefault.onPost('/api/v1/auth/refresh').reply(401, { code: 401, message: 'invalid refresh', data: null })
    mockHttp.onGet('/api/v1/system/users').reply(401, { code: 401, message: 'unauthorized', data: null })
    await expect(http.get('/system/users')).rejects.toBeTruthy()
    expect(localStorage.getItem('lark_access_token')).toBeNull()
    expect(localStorage.getItem('lark_refresh_token')).toBeNull()
    expect(window.location.href).toBe('/login')
  })

  it('concurrent 401s share a single refresh call', async () => {
    setTokens('expired-access', 'refresh-1')
    let refreshCount = 0
    mockDefault.onPost('/api/v1/auth/refresh').reply(() => {
      refreshCount += 1
      return [200, REFRESH_OK]
    })
    const calls: Record<string, number> = {}
    mockHttp.onGet('/api/v1/system/users').reply((config) => {
      calls['/system/users'] = (calls['/system/users'] ?? 0) + 1
      if (calls['/system/users'] === 1) return [401, { code: 401, message: 'unauthorized', data: null }]
      return [200, { code: 0, message: 'ok', data: { list: [], total: 0, page: 1, size: 10 } }]
    })
    mockHttp.onGet('/api/v1/system/roles').reply((config) => {
      calls['/system/roles'] = (calls['/system/roles'] ?? 0) + 1
      if (calls['/system/roles'] === 1) return [401, { code: 401, message: 'unauthorized', data: null }]
      return [200, { code: 0, message: 'ok', data: [] }]
    })
    const [a, b] = await Promise.allSettled([http.get('/system/users'), http.get('/system/roles')])
    expect(a.status).toBe('fulfilled')
    expect(b.status).toBe('fulfilled')
    expect(refreshCount).toBe(1)
  })

  it('401 without refresh token does not hang and rejects', async () => {
    setTokens('expired-access', '')
    mockHttp.onGet('/api/v1/system/users').reply(401, { code: 401, message: 'unauthorized', data: null })
    await expect(http.get('/system/users')).rejects.toBeTruthy()
    expect(localStorage.getItem('lark_access_token')).toBeNull()
  })

  it('request() unwraps Result.data on code 0', async () => {
    mockHttp.onGet('/api/v1/auth/me').reply(200, {
      code: 0,
      message: 'ok',
      data: { id: 1, username: 'admin', real_name: 'Admin', roles: [], permissions: [], visible_group_ids: [], is_admin: true },
    })
    const data = await request<{ id: number; username: string }>({ url: '/auth/me', method: 'get' })
    expect(data.id).toBe(1)
    expect(data.username).toBe('admin')
  })

  it('request() throws on non-zero code', async () => {
    mockHttp.onGet('/api/v1/system/users').reply(200, { code: 500, message: 'boom', data: null })
    await expect(request({ url: '/system/users', method: 'get' })).rejects.toThrow('boom')
  })

  it('extractError prefers Result.message for axios errors', () => {
    const error = new Error('Network Error') as Error & { isAxiosError?: boolean; response?: unknown }
    error.isAxiosError = true
    error.response = { data: { code: 500, message: 'server exploded', data: null } }
    expect(extractError(error)).toBe('server exploded')
  })

  it('extractError falls back to error message', () => {
    expect(extractError(new Error('plain'))).toBe('plain')
    expect(extractError('unexpected')).toBe('请求失败')
  })
})
