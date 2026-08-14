import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, getMe, logout as apiLogout, refresh } from '../api/auth'
import { getTokens, setTokens, clearTokens, hasToken } from '../api/tokens'
import type { LoginIn, UserMe } from '../api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserMe | null>(null)
  const loaded = ref(false)

  const isLoggedIn = computed(() => hasToken())
  const isAdmin = computed(() => user.value?.is_admin ?? false)
  const permissions = computed(() => user.value?.permissions ?? [])

  function hasPerm(code: string): boolean {
    if (isAdmin.value) return true
    return permissions.value.includes(code)
  }

  async function login(data: LoginIn): Promise<void> {
    const result = await apiLogin(data)
    setTokens(result.access_token, result.refresh_token)
    user.value = result.user
    loaded.value = true
  }

  async function fetchMe(): Promise<void> {
    if (!hasToken()) {
      loaded.value = true
      return
    }
    try {
      user.value = await getMe()
    } finally {
      loaded.value = true
    }
  }

  async function tryRefresh(): Promise<boolean> {
    const { refresh_token } = getTokens()
    if (!refresh_token) return false
    try {
      const result = await refresh(refresh_token)
      setTokens(result.access_token, result.refresh_token)
      user.value = result.user
      loaded.value = true
      return true
    } catch {
      clearTokens()
      user.value = null
      loaded.value = true
      return false
    }
  }

  async function logout(): Promise<void> {
    try {
      await apiLogout()
    } catch {
      // ignore network errors on logout
    }
    clearTokens()
    user.value = null
  }

  return { user, loaded, isLoggedIn, isAdmin, permissions, hasPerm, login, fetchMe, tryRefresh, logout }
})
