<template>
  <div class="callback-page" v-loading="true" element-loading-text="登录中…"></div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { clearTokens } from '../api/tokens'

const router = useRouter()
const auth = useAuthStore()

function parseHash(hash: string): Record<string, string> {
  const raw = hash.startsWith('#') ? hash.slice(1) : hash
  const params = new URLSearchParams(raw.startsWith('?') ? raw.slice(1) : raw)
  const out: Record<string, string> = {}
  params.forEach((value, key) => {
    out[key] = value
  })
  return out
}

function clearHash(): void {
  if (window.location.hash) {
    history.replaceState(null, '', window.location.pathname + window.location.search)
  }
}

onMounted(async () => {
  const params = parseHash(window.location.hash)
  const accessToken = params.access_token || params.token || ''
  const refreshToken = params.refresh_token || ''
  clearHash()
  if (!accessToken) {
    router.replace('/login')
    return
  }
  try {
    await auth.loginWithTokens(accessToken, refreshToken)
    router.replace('/')
  } catch {
    clearTokens()
    router.replace('/login')
  }
})
</script>

<style scoped>
.callback-page {
  height: 100vh;
}
</style>
