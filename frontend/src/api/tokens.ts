export interface Tokens {
  access_token: string
  refresh_token: string
}

const ACCESS_KEY = 'lark_access_token'
const REFRESH_KEY = 'lark_refresh_token'

export function getTokens(): Tokens {
  return {
    access_token: localStorage.getItem(ACCESS_KEY) ?? '',
    refresh_token: localStorage.getItem(REFRESH_KEY) ?? '',
  }
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export function hasToken(): boolean {
  return Boolean(localStorage.getItem(ACCESS_KEY))
}
