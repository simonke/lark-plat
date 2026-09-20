import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { vPerm } from '../src/directives/perm'
import { useAuthStore } from '../src/stores/auth'

vi.mock('../src/api/authProviders', () => ({
  listAuthProviders: vi.fn(),
  createAuthProvider: vi.fn(),
  updateAuthProvider: vi.fn(),
  deleteAuthProvider: vi.fn(),
  setAuthProviderStatus: vi.fn(),
  testAuthProvider: vi.fn(),
}))

import * as providersApi from '../src/api/authProviders'
import AuthProvidersView from '../src/views/system/AuthProvidersView.vue'

function setAdmin() {
  const store = useAuthStore()
  store.user = {
    id: 1,
    username: 'admin',
    real_name: 'Admin',
    roles: [],
    permissions: [],
    visible_group_ids: [],
    is_admin: true,
  }
  store.loaded = true
}

function mountView() {
  return mount(AuthProvidersView, {
    global: { plugins: [ElementPlus], directives: { perm: vPerm } },
  })
}

describe('AuthProvidersView (P2-3 identity providers)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    setAdmin()
  })

  it('renders provider rows with masked config keys (no plaintext secrets)', async () => {
    vi.mocked(providersApi.listAuthProviders).mockResolvedValue([
      {
        id: 1,
        code: 'corp-ldap',
        name: '企业 LDAP',
        type: 'ldap',
        enabled: 1,
        config_mask: { server_uri: '****', password: '****' },
        created_at: '2026-09-20T00:00:00Z',
      },
    ])

    const wrapper = mountView()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('企业 LDAP')
    expect(text).toContain('corp-ldap')
    expect(text).toContain('server_uri')
    expect(text).toContain('password')
    expect(text).not.toContain('ldaps://')
    wrapper.unmount()
  })

  it('试测 calls the provider test endpoint (not a plaintext echo)', async () => {
    vi.mocked(providersApi.listAuthProviders).mockResolvedValue([
      { id: 7, code: 'corp-oauth', name: 'SSO', type: 'oauth2', enabled: 1, config_mask: {}, created_at: '2026-09-20T00:00:00Z' },
    ])
    vi.mocked(providersApi.testAuthProvider).mockResolvedValue({ ok: true, latency_ms: 5 })

    const wrapper = mountView()
    await flushPromises()

    const testBtn = wrapper.findAll('button').find((b) => b.text().includes('试测'))
    expect(testBtn).toBeTruthy()
    await testBtn!.trigger('click')
    await flushPromises()

    expect(providersApi.testAuthProvider).toHaveBeenCalledWith(7)
    wrapper.unmount()
  })
})
