/**
 * Identity provider API (P2-3 LDAP / OAuth2 SSO).
 * Contract: api-design v3 §3, architecture-phase23 §5.
 * Provider config is write-only; reads return a masked `config_mask`. On edit,
 * omitting `config` keeps the existing ciphertext ("密文留空＝保留").
 */
import { request } from './http'
import type {
  AuthProviderBrief,
  AuthProviderCreate,
  AuthProviderOut,
  AuthProviderStatusIn,
  AuthProviderTestResult,
  AuthProviderUpdate,
} from './types'

/** Admin management list (authenticated): full rows. */
export const listAuthProviders = (): Promise<AuthProviderOut[]> =>
  request({ url: '/auth/providers', method: 'get' })

/** Login-page provider list (anonymous): `{code,type,name}` incl. built-in `local`. */
export const listLoginProviders = (): Promise<AuthProviderBrief[]> =>
  request({ url: '/auth/providers', method: 'get' })

export const createAuthProvider = (data: AuthProviderCreate): Promise<AuthProviderOut> =>
  request({ url: '/auth/providers', method: 'post', data })

export const updateAuthProvider = (providerId: number, data: AuthProviderUpdate): Promise<null> =>
  request({ url: `/auth/providers/${providerId}`, method: 'put', data })

export const deleteAuthProvider = (providerId: number): Promise<null> =>
  request({ url: `/auth/providers/${providerId}`, method: 'delete' })

export const setAuthProviderStatus = (providerId: number, data: AuthProviderStatusIn): Promise<null> =>
  request({ url: `/auth/providers/${providerId}/status`, method: 'put', data })

export const testAuthProvider = (providerId: number): Promise<AuthProviderTestResult> =>
  request({ url: `/auth/providers/${providerId}/test`, method: 'post' })
