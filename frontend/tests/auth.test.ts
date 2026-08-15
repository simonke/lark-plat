import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore } from '../src/stores/auth'
import { setTokens, clearTokens } from '../src/api/tokens'

vi.mock('../src/api/auth', () => ({
  login: vi.fn(),
  getMe: vi.fn(),
  logout: vi.fn(),
  refresh: vi.fn(),
}))

import * as authApi from '../src/api/auth'

const fullMe = {
  id: 1,
  username: 'admin',
  real_name: 'Admin',
  roles: [],
  permissions: ['system:user:list', 'system:role:list'],
  visible_group_ids: [1, 2],
  is_admin: false,
}

const adminMe = { ...fullMe, is_admin: true, permissions: [] }

describe('auth store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    clearTokens()
    vi.clearAllMocks()
  })

  it('login stores tokens and loads full user via fetchMe', async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-1',
      refresh_token: 'refresh-1',
      token_type: 'bearer',
      user: { id: 1, username: 'admin', real_name: 'Admin', roles: [] },
    })
    vi.mocked(authApi.getMe).mockResolvedValue(fullMe)

    const store = useAuthStore()
    expect(store.loaded).toBe(false)
    await store.login({ username: 'admin', password: 'p' })

    expect(localStorage.getItem('lark_access_token')).toBe('access-1')
    expect(localStorage.getItem('lark_refresh_token')).toBe('refresh-1')
    expect(authApi.getMe).toHaveBeenCalledTimes(1)
    expect(store.user).toEqual(fullMe)
    expect(store.loaded).toBe(true)
    expect(store.isLoggedIn).toBe(true)
  })

  it('hasPerm returns true for admin regardless of permission list', () => {
    vi.mocked(authApi.getMe).mockResolvedValue(adminMe)
    const store = useAuthStore()
    store.user = adminMe
    store.loaded = true
    expect(store.isAdmin).toBe(true)
    expect(store.hasPerm('anything:not:listed')).toBe(true)
  })

  it('hasPerm matches permission list for non-admin', () => {
    const store = useAuthStore()
    store.user = fullMe
    store.loaded = true
    expect(store.hasPerm('system:user:list')).toBe(true)
    expect(store.hasPerm('system:user:del')).toBe(false)
  })

  it('fetchMe without token marks loaded without calling API', async () => {
    const store = useAuthStore()
    await store.fetchMe()
    expect(store.loaded).toBe(true)
    expect(authApi.getMe).not.toHaveBeenCalled()
  })

  it('fetchMe with token loads full user', async () => {
    setTokens('access-1', 'refresh-1')
    vi.mocked(authApi.getMe).mockResolvedValue(fullMe)
    const store = useAuthStore()
    await store.fetchMe()
    expect(store.user).toEqual(fullMe)
    expect(store.loaded).toBe(true)
  })

  it('tryRefresh succeeds and reloads user', async () => {
    setTokens('expired-access', 'refresh-1')
    vi.mocked(authApi.refresh).mockResolvedValue({
      access_token: 'new-access',
      refresh_token: 'new-refresh',
      token_type: 'bearer',
      user: { id: 1, username: 'admin', real_name: 'Admin', roles: [] },
    })
    vi.mocked(authApi.getMe).mockResolvedValue(fullMe)
    const store = useAuthStore()
    const ok = await store.tryRefresh()
    expect(ok).toBe(true)
    expect(localStorage.getItem('lark_access_token')).toBe('new-access')
    expect(authApi.getMe).toHaveBeenCalledTimes(1)
    expect(store.loaded).toBe(true)
  })

  it('tryRefresh fails clears tokens and returns false', async () => {
    setTokens('expired-access', 'expired-refresh')
    vi.mocked(authApi.refresh).mockRejectedValue(new Error('invalid refresh'))
    const store = useAuthStore()
    const ok = await store.tryRefresh()
    expect(ok).toBe(false)
    expect(localStorage.getItem('lark_access_token')).toBeNull()
    expect(store.user).toBeNull()
    expect(store.loaded).toBe(true)
  })

  it('logout clears tokens and user', async () => {
    setTokens('access-1', 'refresh-1')
    const store = useAuthStore()
    store.user = fullMe
    await store.logout()
    expect(localStorage.getItem('lark_access_token')).toBeNull()
    expect(store.user).toBeNull()
  })
})
