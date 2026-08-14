import { request } from './http'
import type { ChangePasswordIn, LoginIn, TokenOut, UserMe } from './types'

export const login = (data: LoginIn): Promise<TokenOut> => request({ url: '/auth/login', method: 'post', data })

export const refresh = (refresh_token: string): Promise<TokenOut> =>
  request({ url: '/auth/refresh', method: 'post', data: { refresh_token } })

export const logout = (): Promise<null> => request({ url: '/auth/logout', method: 'post' })

export const getMe = (): Promise<UserMe> => request({ url: '/auth/me', method: 'get' })

export const changePassword = (data: ChangePasswordIn): Promise<null> =>
  request({ url: '/auth/password', method: 'put', data })
