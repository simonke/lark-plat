import axios, { AxiosError, type AxiosInstance, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import type { Result } from './types'
import { getTokens, setTokens, clearTokens } from './tokens'

let refreshing: Promise<string> | null = null

async function doRefresh(): Promise<string> {
  const { refresh_token } = getTokens()
  if (!refresh_token) {
    throw new AxiosError('no refresh token', '401')
  }
  const resp = await axios.post('/api/v1/auth/refresh', { refresh_token })
  const result: Result<{ access_token: string; refresh_token: string; token_type: string }> = resp.data
  if (result.code !== 0) {
    throw new AxiosError(result.message, '401')
  }
  setTokens(result.data.access_token, result.data.refresh_token)
  return result.data.access_token
}

function refreshAccess(): Promise<string> {
  refreshing ??= doRefresh().finally(() => {
    refreshing = null
  })
  return refreshing
}

function isAuthPath(url?: string): boolean {
  return !url || url.includes('/auth/login') || url.includes('/auth/refresh')
}

const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const { access_token } = getTokens()
  if (access_token) {
    config.headers.Authorization = `Bearer ${access_token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<Result>) => {
    const config = error.config as (AxiosRequestConfig & { _retried?: boolean }) | undefined
    const status = error.response?.status
    if (status === 401 && config && !config._retried && !isAuthPath(config.url)) {
      config._retried = true
      try {
        const token = await refreshAccess()
        config.headers = { ...config.headers, Authorization: `Bearer ${token}` }
        return http.request(config)
      } catch {
        clearTokens()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
      }
    }
    if (status === 401) {
      clearTokens()
    }
    return Promise.reject(error)
  },
)

export default http

export { http }

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const resp = await http.request<Result<T>>(config)
  const result = resp.data
  if (result.code !== 0) {
    throw new Error(result.message || 'request failed')
  }
  return result.data
}

export function extractError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const result = error.response?.data as Result | undefined
    return result?.message || error.message || '请求失败'
  }
  return error instanceof Error ? error.message : '请求失败'
}
