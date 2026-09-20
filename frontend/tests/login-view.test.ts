import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: pushMock }) }))

vi.mock('../src/api/authProviders', () => ({
  listLoginProviders: vi.fn(),
}))

import * as providersApi from '../src/api/authProviders'
import LoginView from '../src/views/LoginView.vue'

function mountView() {
  return mount(LoginView, { global: { plugins: [ElementPlus] } })
}

describe('LoginView (P2-3 multi-provider dispatch)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('falls back to local password form when only local is available', async () => {
    vi.mocked(providersApi.listLoginProviders).mockResolvedValue([{ code: 'local', type: 'local', name: '账号密码' }])

    const wrapper = mountView()
    await flushPromises()

    expect(providersApi.listLoginProviders).toHaveBeenCalledTimes(1)
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('renders a selector for multiple providers and shows password form for the default local', async () => {
    vi.mocked(providersApi.listLoginProviders).mockResolvedValue([
      { code: 'local', type: 'local', name: '账号密码' },
      { code: 'corp-ldap', type: 'ldap', name: '企业 LDAP' },
      { code: 'corp-oauth', type: 'oauth2', name: '单点登录' },
    ])

    const wrapper = mountView()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('账号密码')
    expect(text).toContain('企业 LDAP')
    expect(text).toContain('单点登录')
    expect(wrapper.findAll('input[type="radio"]').length).toBeGreaterThanOrEqual(3)
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('falls back to local when the provider list request fails', async () => {
    vi.mocked(providersApi.listLoginProviders).mockRejectedValue(new Error('network'))

    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('lark-plat 登录')
    expect(wrapper.find('input[autocomplete="username"]').exists()).toBe(true)
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
