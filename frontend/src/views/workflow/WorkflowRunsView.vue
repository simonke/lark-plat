<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">运行记录</span>
        </div>
      </template>

      <el-form inline :model="query" @submit.prevent="load(1)">
        <el-form-item label="编排 ID">
          <el-input
            v-model.number="query.workflow_id"
            placeholder="workflow_id"
            clearable
            style="width: 140px"
            @keyup.enter="load(1)"
          />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" clearable placeholder="全部" style="width: 140px">
            <el-option v-for="s in RUN_STATUS_OPTIONS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="load(1)">查询</el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" v-loading="loading" border @row-click="openDetail">
        <el-table-column prop="id" label="运行 ID" width="90" />
        <el-table-column prop="workflow_id" label="编排 ID" width="90" />
        <el-table-column label="版本" width="80">
          <template #default="{ row }">v{{ row.workflow_version }}</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="runStatusTag(row.status)" size="small">{{ runStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="触发方式" width="110">
          <template #default="{ row }">{{ triggerLabel(row.trigger_type) }}</template>
        </el-table-column>
        <el-table-column label="开始时间" width="180">
          <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="结束时间" width="180">
          <template #default="{ row }">{{ formatTime(row.finished_at) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next, sizes"
        :total="total"
        v-model:current-page="query.page"
        v-model:page-size="query.size"
        :page-sizes="[10, 20, 50]"
        @change="load()"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listWorkflowRuns } from '../../api/workflow'
import { extractError } from '../../api/http'
import type { WorkflowRun, WorkflowRunQuery } from '../../api/types'
import { RUN_STATUS_OPTIONS, formatTime, runStatusLabel, runStatusTag, triggerLabel } from './helpers'

const router = useRouter()
const loading = ref(false)
const rows = ref<WorkflowRun[]>([])
const total = ref(0)
const query = reactive<WorkflowRunQuery>({ page: 1, size: 10 })

async function load(page?: number) {
  if (page) query.page = page
  loading.value = true
  try {
    const res = await listWorkflowRuns({
      workflow_id: typeof query.workflow_id === 'number' ? query.workflow_id : undefined,
      status: query.status || undefined,
      page: query.page,
      size: query.size,
    })
    rows.value = res.list
    total.value = res.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

function reset() {
  query.workflow_id = undefined
  query.status = undefined
  query.page = 1
  load()
}

function openDetail(row: WorkflowRun) {
  router.push(`/workflow-runs/${row.id}`)
}

onMounted(() => load(1))
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
</style>
