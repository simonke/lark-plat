<template>
  <div class="dashboard-view">
    <h3>仪表盘</h3>
    
    <el-row :gutter="20" class="stats-row">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #409eff">
              <el-icon :size="24"><Monitor /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.total || 0 }}</div>
              <div class="stat-label">主机总数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #67c23a">
              <el-icon :size="24"><CircleCheck /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.online || 0 }}</div>
              <div class="stat-label">在线主机</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #f56c6c">
              <el-icon :size="24"><CircleClose /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ stats?.offline || 0 }}</div>
              <div class="stat-label">离线主机</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-content">
            <div class="stat-icon" style="background: #e6a23c">
              <el-icon :size="24"><Collection /></el-icon>
            </div>
            <div class="stat-info">
              <div class="stat-value">{{ envCount }}</div>
              <div class="stat-label">环境数量</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="quick-actions">
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>快速操作</span>
          </template>
          <div class="action-list">
            <el-button type="primary" @click="$router.push('/assets/hosts')" v-if="auth.hasPerm('asset:host:list')">
              <el-icon><Monitor /></el-icon> 主机管理
            </el-button>
            <el-button type="success" @click="$router.push('/assets/groups')" v-if="auth.hasPerm('asset:group:list')">
              <el-icon><Folder /></el-icon> 分组管理
            </el-button>
            <el-button type="warning" @click="$router.push('/assets/credentials')" v-if="auth.hasPerm('asset:cred:list')">
              <el-icon><Key /></el-icon> 凭据管理
            </el-button>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>环境分布</span>
          </template>
          <div class="env-list">
            <div v-for="(count, env) in stats?.by_env" :key="env" class="env-item">
              <span class="env-name">{{ envLabel(String(env)) }}</span>
              <el-progress :percentage="envPercent(count)" :stroke-width="18" :text-inside="true" />
            </div>
            <el-empty v-if="!stats?.by_env || Object.keys(stats.by_env).length === 0" description="暂无数据" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Monitor, CircleCheck, CircleClose, Collection, Folder, Key } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { getHostStats } from '../api/assets'
import type { HostStats } from '../api/types'

const auth = useAuthStore()

const stats = ref<HostStats | null>(null)

const envCount = computed(() => {
  if (!stats.value?.by_env) return 0
  return Object.keys(stats.value.by_env).length
})

function envLabel(env: string) {
  const map: Record<string, string> = { production: '生产', testing: '测试', development: '开发' }
  return map[env] || env
}

function envPercent(count: number) {
  if (!stats.value?.total) return 0
  return Math.round((count / stats.value.total) * 100)
}

onMounted(async () => {
  try {
    stats.value = await getHostStats()
  } catch {
    // ignore
  }
})
</script>

<style scoped>
.dashboard-view {
  padding: 20px;
}
.stats-row {
  margin-bottom: 20px;
}
.stat-card {
  cursor: pointer;
}
.stat-content {
  display: flex;
  align-items: center;
  gap: 16px;
}
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}
.stat-info {
  flex: 1;
}
.stat-value {
  font-size: 28px;
  font-weight: 600;
  line-height: 1.2;
}
.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}
.quick-actions {
  margin-bottom: 20px;
}
.action-list {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.env-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.env-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.env-name {
  width: 60px;
  font-size: 14px;
}
</style>