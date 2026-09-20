import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listAuthProviders,
  listLoginProviders,
  createAuthProvider,
  updateAuthProvider,
  deleteAuthProvider,
  setAuthProviderStatus,
  testAuthProvider,
} from '../src/api/authProviders'

vi.mock('../src/api/http', () => ({ request: vi.fn() }))

import { request } from '../src/api/http'

describe('Auth providers API (P2-3 / auth §3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('listAuthProviders → GET /auth/providers', async () => {
    vi.mocked(request).mockResolvedValue([])
    await listAuthProviders()
    expect(request).toHaveBeenCalledWith({ url: '/auth/providers', method: 'get' })
  })

  it('listLoginProviders → GET /auth/providers', async () => {
    vi.mocked(request).mockResolvedValue([])
    await listLoginProviders()
    expect(request).toHaveBeenCalledWith({ url: '/auth/providers', method: 'get' })
  })

  it('createAuthProvider → POST /auth/providers with {name,type,code,config,enabled}', async () => {
    vi.mocked(request).mockResolvedValue({ id: 1 })
    const payload = { name: 'corp-ldap', type: 'ldap' as const, code: 'corp', config: { server_uri: 'ldaps://x' }, enabled: 1 }
    await createAuthProvider(payload)
    expect(request).toHaveBeenCalledWith({ url: '/auth/providers', method: 'post', data: payload })
  })

  it('updateAuthProvider omits config to keep existing ciphertext (密文留空＝保留)', async () => {
    vi.mocked(request).mockResolvedValue(null)
    await updateAuthProvider(5, { name: 'renamed' })
    expect(request).toHaveBeenCalledWith({ url: '/auth/providers/5', method: 'put', data: { name: 'renamed' } })
  })

  it('deleteAuthProvider → DELETE /auth/providers/{id}', async () => {
    vi.mocked(request).mockResolvedValue(null)
    await deleteAuthProvider(9)
    expect(request).toHaveBeenCalledWith({ url: '/auth/providers/9', method: 'delete' })
  })

  it('setAuthProviderStatus → PUT /auth/providers/{id}/status', async () => {
    vi.mocked(request).mockResolvedValue(null)
    await setAuthProviderStatus(3, { enabled: 0 })
    expect(request).toHaveBeenCalledWith({ url: '/auth/providers/3/status', method: 'put', data: { enabled: 0 } })
  })

  it('testAuthProvider → POST /auth/providers/{id}/test', async () => {
    vi.mocked(request).mockResolvedValue({ ok: true, latency_ms: 12 })
    const result = await testAuthProvider(2)
    expect(request).toHaveBeenCalledWith({ url: '/auth/providers/2/test', method: 'post' })
    expect(result.ok).toBe(true)
  })
})
