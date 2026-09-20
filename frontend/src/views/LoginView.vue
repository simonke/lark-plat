<template>
  <div class="login-page">
    <el-card style="max-width: 400px; margin: 120px auto">
      <template #header>
        <h2 style="margin: 0">lark-plat 登录</h2>
      </template>

      <el-radio-group v-if="providers.length > 1" v-model="selected" class="providers">
        <el-radio-button v-for="p in providers" :key="p.code" :value="p.code">{{ p.name }}</el-radio-button>
      </el-radio-group>

      <el-form v-if="isPasswordType" :model="form" label-width="80px" @submit.prevent="onSubmit">
        <el-form-item label="用户名">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" autocomplete="current-password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="onSubmit">登录</el-button>
        </el-form-item>
      </el-form>

      <div v-else class="oauth">
        <el-button type="primary" @click="onOauthLogin">使用 {{ currentProvider?.name }} 登录</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { listLoginProviders } from '../api/authProviders'
import { extractError } from '../api/http'
import type { AuthProviderBrief } from '../api/types'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const LOCAL: AuthProviderBrief = { code: 'local', type: 'local', name: '账号密码' }
const providers = ref<AuthProviderBrief[]>([LOCAL])
const selected = ref('local')

const currentProvider = computed(() => providers.value.find((p) => p.code === selected.value))
const isPasswordType = computed(() => (currentProvider.value?.type ?? 'local') !== 'oauth2')

async function loadProviders() {
  try {
    const list = await listLoginProviders()
    providers.value = list && list.length > 0 ? list : [LOCAL]
  } catch {
    providers.value = [LOCAL]
  }
  if (!providers.value.some((p) => p.code === selected.value)) {
    selected.value = providers.value[0].code
  }
}

const onSubmit = async () => {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    if (currentProvider.value?.type === 'ldap') {
      await auth.ldapLogin(form)
    } else {
      await auth.login(form)
    }
    router.push('/')
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

const onOauthLogin = () => {
  const code = currentProvider.value?.code
  if (!code) return
  window.location.href = '/api/v1/auth/oauth/' + code + '/login'
}

onMounted(loadProviders)
</script>

<style scoped>
.providers {
  margin-bottom: 16px;
  display: flex;
  flex-wrap: wrap;
}
.oauth {
  text-align: center;
  padding: 8px 0;
}
</style>
