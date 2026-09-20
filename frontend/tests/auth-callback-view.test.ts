import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { replaceMock, loginWithTokensMock } = vi.hoisted(() => ({
  replaceMock: vi.fn(),
  loginWithTokensMock: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ replace: replaceMock }) }))
vi.mock('../src/stores/auth', () => ({
  useAuthStore: () => ({ loginWithTokens: loginWithTokensMock }),
}))

import AuthCallbackView from '../src/views/AuthCallbackView.vue'

function mountView() {
  return mount(AuthCallbackView, { global: { plugins: [ElementPlus] } })
}

describe('AuthCallbackView (P2-3 oauth callback)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    loginWithTokensMock.mockResolvedValue(undefined)
    window.history.replaceState(null, '', '/')
  })

  it('reads hash, adopts tokens, clears hash immediately and routes home', async () => {
    window.history.replaceState(null, '', '/auth/callback#access_token=acc-1&refresh_token=ref-1')

    const wrapper = mountView()
    await flushPromises()

    expect(loginWithTokensMock).toHaveBeenCalledWith('acc-1', 'ref-1')
    expect(window.location.hash).toBe('')
    expect(replaceMock).toHaveBeenCalledWith('/')
    wrapper.unmount()
  })

  it('missing access token routes back to login without adopting tokens', async () => {
    window.history.replaceState(null, '', '/auth/callback#state=abc')

    const wrapper = mountView()
    await flushPromises()

    expect(loginWithTokensMock).not.toHaveBeenCalled()
    expect(replaceMock).toHaveBeenCalledWith('/login')
    wrapper.unmount()
  })

  it('tolerates a bare #token=<access> hash shape', async () => {
    window.history.replaceState(null, '', '/auth/callback#token=acc-2')

    const wrapper = mountView()
    await flushPromises()

    expect(loginWithTokensMock).toHaveBeenCalledWith('acc-2', '')
    wrapper.unmount()
  })
})
