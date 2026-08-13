<template>
  <el-card style="max-width: 400px; margin: 120px auto">
    <template #header>
      <h2 style="margin: 0">lark-plat 登录</h2>
    </template>
    <el-form :model="form" label-width="80px" @submit.prevent="onSubmit">
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
  </el-card>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api/auth'

const router = useRouter()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

const onSubmit = async () => {
  loading.value = true
  try {
    const res: any = await login(form)
    localStorage.setItem('lark_token', res.data.access_token)
    router.push('/')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.message ?? '登录失败')
  } finally {
    loading.value = false
  }
}
</script>
