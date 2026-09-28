import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import CredentialsView from '../src/views/assets/CredentialsView.vue'
import HostDetailView from '../src/views/assets/HostDetailView.vue'
import { vPerm } from '../src/directives/perm'
import { buildCredentialCreatePayload, clearNonApplicableSecretFields } from '../src/views/assets/credentialForm'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: '1' } }),
  useRouter: () => ({ push: vi.fn() })
}))

vi.mock('../src/api/assets', () => ({
  getHosts: vi.fn(),
  getHost: vi.fn(),
  checkConnection: vi.fn(),
  getCredentials: vi.fn(),
  createCredential: vi.fn(),
  updateCredential: vi.fn(),
  deleteCredential: vi.fn()
}))

vi.mock('../src/api/http', () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  extractError: vi.fn(() => 'err')
}))

import * as assetsApi from '../src/api/assets'
import { useAuthStore } from '../src/stores/auth'

const credRow = {
  id: 1,
  host_id: 1,
  host_hostname: 'host-1',
  username: 'admin',
  type: 'password',
  secret_mask: '***',
  created_at: '2026-09-28T10:00:00+08:00'
}

const hostRow = {
  id: 1,
  hostname: 'host-1',
  ip: '1.1.1.1',
  os_type: 'linux',
  os_version: 'Ubuntu 22.04',
  group_id: 1,
  group_name: 'prod',
  env: 'production',
  status: 'online',
  connector: 'agent',
  sensitivity_level: 'normal',
  tags: [],
  remark: '',
  created_at: '2026-09-28T10:00:00+08:00',
  updated_at: '2026-09-28T10:00:00+08:00'
}

const stubGlobals = {
  global: {
    plugins: [ElementPlus],
    directives: { perm: vPerm },
    stubs: { teleport: true, ElSelect: true, ElOption: true }
  }
}

function mountView() {
  return mount(CredentialsView, stubGlobals)
}

function mountHostDetail() {
  return mount(HostDetailView, stubGlobals)
}

function adminStore() {
  const store = useAuthStore()
  store.user = {
    id: 1,
    username: 'admin',
    real_name: 'Admin',
    roles: [],
    permissions: [],
    visible_group_ids: [],
    is_admin: true
  }
  store.loaded = true
  return store
}

function buttonByText(wrapper: ReturnType<typeof mountView>, text: string) {
  return wrapper.findAll('button').find((b) => b.text().includes(text))
}

describe('B1 create payload construction (type-conditional)', () => {
  it('password type drops non-applicable key/passphrase even with non-empty residue', () => {
    const payload = buildCredentialCreatePayload({
      host_id: 1,
      username: 'u',
      type: 'password',
      secret: 'pw',
      key: 'RESIDUAL-KEY',
      passphrase: 'RESIDUAL-PASS'
    })
    expect(payload).toEqual({ host_id: 1, username: 'u', type: 'password', secret: 'pw' })
    expect(payload.key).toBeUndefined()
    expect(payload.passphrase).toBeUndefined()
  })

  it('key type drops non-applicable secret even with non-empty residue', () => {
    const payload = buildCredentialCreatePayload({
      host_id: 2,
      username: 'u2',
      type: 'key',
      secret: 'RESIDUAL-SECRET',
      key: 'PRIVATE-KEY',
      passphrase: 'pass'
    })
    expect(payload).toEqual({ host_id: 2, username: 'u2', type: 'key', key: 'PRIVATE-KEY', passphrase: 'pass' })
    expect(payload.secret).toBeUndefined()
  })

  it('clearNonApplicableSecretFields blanks all three fields on type switch', () => {
    const form = { type: 'key' as const, secret: 's', key: 'k', passphrase: 'p' }
    clearNonApplicableSecretFields(form)
    expect(form).toEqual({ type: 'key', secret: '', key: '', passphrase: '' })
  })
})

describe('B1 credential type select is locked in edit mode', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('CredentialsView: create mode editable, edit mode disabled', async () => {
    adminStore()
    vi.mocked(assetsApi.getCredentials).mockResolvedValue([credRow])
    vi.mocked(assetsApi.getHosts).mockResolvedValue({ list: [{ id: 1, hostname: 'host-1', ip: '1.1.1.1' }], total: 1, page: 1, size: 1000 })

    const wrapper = mountView()
    await flushPromises()

    await buttonByText(wrapper, '新增凭据')!.trigger('click')
    await flushPromises()
    let selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects[selects.length - 1].props('disabled')).toBeFalsy()

    await buttonByText(wrapper, '编辑')!.trigger('click')
    await flushPromises()
    selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects).toHaveLength(1)
    expect(selects[0].props('disabled')).toBe(true)
  })

  it('HostDetailView: edit mode disables the credential type select', async () => {
    adminStore()
    vi.mocked(assetsApi.getHost).mockResolvedValue(hostRow as never)
    vi.mocked(assetsApi.getCredentials).mockResolvedValue([credRow])

    const wrapper = mountHostDetail()
    await flushPromises()

    await buttonByText(wrapper, '编辑')!.trigger('click')
    await flushPromises()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects).toHaveLength(1)
    expect(selects[0].props('disabled')).toBe(true)
  })
})
