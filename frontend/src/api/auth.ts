import http from '../api/http'

export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  refresh_token: string
  expires_in: number
  user: { id: number; username: string; real_name: string }
}

export const login = (data: LoginParams) => http.post('/auth/login', data)
export const getMe = () => http.get('/auth/me')
export const logout = () => http.post('/auth/logout')
