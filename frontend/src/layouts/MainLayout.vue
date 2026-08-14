<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="logo">lark-plat</div>
      <el-menu :default-active="activePath" router>
        <el-menu-item index="/dashboard">
          <el-icon><DataBoard /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-sub-menu index="system">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>系统管理</span>
          </template>
          <el-menu-item index="/system/users" v-if="auth.hasPerm('system:user:list')">用户管理</el-menu-item>
          <el-menu-item index="/system/roles" v-if="auth.hasPerm('system:role:list')">角色与权限</el-menu-item>
          <el-menu-item index="/system/audit-logs" v-if="auth.hasPerm('system:audit:list')">审计日志</el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <div class="spacer" />
        <el-dropdown @command="onCommand">
          <span class="user">
            {{ auth.user?.real_name || auth.user?.username }}
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="password">修改密码</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>

  <el-dialog v-model="passwordVisible" title="修改密码" width="420px">
    <el-form :model="pwdForm" label-width="90px">
      <el-form-item label="原密码">
        <el-input v-model="pwdForm.old_password" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="pwdForm.new_password" type="password" show-password />
      </el-form-item>
      <el-form-item label="确认密码">
        <el-input v-model="confirmPassword" type="password" show-password />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="passwordVisible = false">取消</el-button>
      <el-button type="primary" :loading="pwdLoading" @click="onChangePassword">确定</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DataBoard, Setting, ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { changePassword } from '../api/auth'
import { extractError } from '../api/http'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activePath = computed(() => route.path)
const passwordVisible = ref(false)
const pwdLoading = ref(false)
const confirmPassword = ref('')
const pwdForm = reactive({ old_password: '', new_password: '' })

onMounted(async () => {
  if (!auth.loaded) {
    await auth.fetchMe()
  }
})

async function onCommand(command: string) {
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定退出登录吗？', '提示', { type: 'warning' })
    } catch {
      return
    }
    await auth.logout()
    router.push('/login')
  } else if (command === 'password') {
    pwdForm.old_password = ''
    pwdForm.new_password = ''
    confirmPassword.value = ''
    passwordVisible.value = true
  }
}

async function onChangePassword() {
  if (pwdForm.new_password.length < 6) {
    ElMessage.warning('新密码至少 6 位')
    return
  }
  if (pwdForm.new_password !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  pwdLoading.value = true
  try {
    await changePassword(pwdForm)
    ElMessage.success('密码已修改')
    passwordVisible.value = false
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.layout {
  height: 100vh;
}
.aside {
  background: #001529;
}
.logo {
  height: 56px;
  line-height: 56px;
  text-align: center;
  color: #fff;
  font-size: 18px;
  font-weight: 600;
}
.aside :deep(.el-menu) {
  border-right: none;
  background: #001529;
}
.aside :deep(.el-menu-item),
.aside :deep(.el-sub-menu__title) {
  color: rgba(255, 255, 255, 0.7);
}
.aside :deep(.el-menu-item.is-active) {
  color: #fff;
  background: var(--el-color-primary);
}
.header {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  border-bottom: 1px solid var(--el-border-color-light);
}
.spacer {
  flex: 1;
}
.user {
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
}
</style>
