import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, DOMWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { vPerm } from '../src/directives/perm'
import { useAuthStore } from '../src/stores/auth'

vi.mock('../src/api/system', () => ({ listRoles: vi.fn(async () => []) }))

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

function setPerms(perms: string[]) {
  const store = useAuthStore()
  store.user = {
    id: 2,
    username: 'op',
    real_name: 'Op',
    roles: [],
    permissions: perms,
    visible_group_ids: [],
    is_admin: false,
  }
  store.loaded = true
}

function mountView() {
  return mount(AuthProvidersView, {
    global: {
      plugins: [ElementPlus],
      directives: { perm: vPerm },
      stubs: { teleport: true, ElSelect: true, ElOption: true },
    },
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

  it('gates write actions by granular perms (base perm alone hides add/edit/test/del)', async () => {
    setPerms(['system:auth:provider'])
    vi.mocked(providersApi.listAuthProviders).mockResolvedValue([
      { id: 1, code: 'corp-ldap', name: '企业 LDAP', type: 'ldap', enabled: 1, config_mask: {}, created_at: '2026-09-20T00:00:00Z' },
    ])

    const wrapper = mountView()
    await flushPromises()

    const labels = wrapper.findAll('button').map((b) => b.text())
    expect(labels.some((t) => t.includes('新增身份源'))).toBe(false)
    expect(labels.some((t) => t.includes('编辑'))).toBe(false)
    expect(labels.some((t) => t.includes('试测'))).toBe(false)
    expect(labels.some((t) => t.includes('删除'))).toBe(false)
    expect(wrapper.text()).toContain('企业 LDAP')
    wrapper.unmount()
  })

  it('LDAP form exposes service-account bind_dn and submits it in config (v2.1)', async () => {
    vi.mocked(providersApi.listAuthProviders).mockResolvedValue([])
    vi.mocked(providersApi.createAuthProvider).mockResolvedValue({ id: 1 } as never)

    const wrapper = mountView()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增身份源'))
    expect(addBtn).toBeTruthy()
    await addBtn!.trigger('click')
    await flushPromises()

    const nameLabel = wrapper.findAll('.el-form-item__label').find((l) => l.text().trim() === '名称')
    const nameInput = new DOMWrapper(nameLabel!.element.parentElement!.querySelector('input') as HTMLElement)
    await nameInput.setValue('企业 LDAP')

    const bindDnInput = wrapper.find('input[placeholder="cn=svc-readonly,ou=service,dc=example,dc=com"]')
    expect(bindDnInput.exists()).toBe(true)
    await bindDnInput.setValue('cn=svc,ou=service,dc=example,dc=com')

    await wrapper.findAll('button').find((b) => b.text().includes('保存'))!.trigger('click')
    await flushPromises()

    expect(providersApi.createAuthProvider).toHaveBeenCalledTimes(1)
    const arg = vi.mocked(providersApi.createAuthProvider).mock.calls[0][0] as {
      type: string
      config: Record<string, unknown>
    }
    expect(arg.type).toBe('ldap')
    expect(arg.config.bind_dn).toBe('cn=svc,ou=service,dc=example,dc=com')
    wrapper.unmount()
  })
})
