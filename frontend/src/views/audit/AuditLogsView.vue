<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">审计日志</span>
          <el-button type="primary" v-perm="'system:audit:export'" @click="onExport">导出 CSV</el-button>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load">
        <el-form-item label="模块">
          <el-input v-model="query.module" clearable placeholder="如 auth/system" />
        </el-form-item>
        <el-form-item label="操作">
          <el-input v-model="query.action" clearable placeholder="如 login" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="query.username" clearable />
        </el-form-item>
        <el-form-item label="开始">
          <el-date-picker v-model="query.start" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" />
        </el-form-item>
        <el-form-item label="结束">
          <el-date-picker v-model="query.end" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load">查询</el-button>
          <el-button @click="resetQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户" min-width="100" />
        <el-table-column prop="module" label="模块" min-width="90" />
        <el-table-column prop="action" label="操作" min-width="100" />
        <el-table-column prop="method" label="方法" width="70" />
        <el-table-column prop="path" label="路径" min-width="220" show-overflow-tooltip />
        <el-table-column prop="ip" label="IP" min-width="120" />
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status < 400 ? 'success' : 'danger'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="cost_ms" label="耗时(ms)" width="90" />
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">
            {{ new Date(row.created_at).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column label="详情" width="70" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next, sizes"
        :total="total"
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :page-sizes="[10, 20, 50]"
        @change="load"
      />
    </el-card>

    <el-dialog v-model="detailVisible" title="审计详情" width="560px">
      <el-descriptions :column="1" border v-if="current">
        <el-descriptions-item label="ID">{{ current.id }}</el-descriptions-item>
        <el-descriptions-item label="用户">{{ current.username }} (uid={{ current.user_id }})</el-descriptions-item>
        <el-descriptions-item label="模块/操作">{{ current.module }} / {{ current.action }}</el-descriptions-item>
        <el-descriptions-item label="请求">{{ current.method }} {{ current.path }}</el-descriptions-item>
        <el-descriptions-item label="参数">
          <pre class="params">{{ JSON.stringify(current.params, null, 2) || '-' }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="IP / UA">{{ current.ip }} / {{ current.user_agent }}</el-descriptions-item>
        <el-descriptions-item label="状态 / 耗时">{{ current.status }} / {{ current.cost_ms }}ms</el-descriptions-item>
        <el-descriptions-item label="TraceId">{{ current.trace_id }}</el-descriptions-item>
        <el-descriptions-item label="时间">{{ new Date(current.created_at).toLocaleString() }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { exportAuditLogs, listAuditLogs } from '../../api/system'
import type { AuditLogOut, AuditLogQuery } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const rows = ref<AuditLogOut[]>([])
const total = ref(0)
const query = reactive<AuditLogQuery>({ page: 1, size: 10 })

const detailVisible = ref(false)
const current = ref<AuditLogOut | null>(null)

async function load() {
  loading.value = true
  try {
    const page = await listAuditLogs(query)
    rows.value = page.list
    total.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function resetQuery() {
  query.module = undefined
  query.action = undefined
  query.username = undefined
  query.start = undefined
  query.end = undefined
  query.page = 1
  load()
}

function openDetail(row: AuditLogOut) {
  current.value = row
  detailVisible.value = true
}

async function onExport() {
  try {
    await exportAuditLogs(query)
    ElMessage.success('已开始下载')
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(load)
</script>

<style scoped>
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-weight: 600;
}
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.params {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
