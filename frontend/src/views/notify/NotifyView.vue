<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="toolbar">
          <span class="title">通知渠道</span>
          <el-button type="primary" v-perm="'notify:channel:add'" @click="openChannel()">新增渠道</el-button>
        </div>
      </template>
      <el-table :data="channels" v-loading="loading" border>
        <el-table-column prop="name" label="渠道名" min-width="140" />
        <el-table-column prop="type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small">{{ row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="配置（脱敏）" min-width="220">
          <template #default="{ row }">
            <code>{{ JSON.stringify(row.config_mask) }}</code>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled === 1 ? 'success' : 'info'">
              {{ row.enabled === 1 ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button size="small" v-perm="'notify:channel:edit'" @click="openChannel(row)">编辑</el-button>
            <el-button size="small" v-perm="'notify:channel:edit'" @click="toggleChannel(row)">
              {{ row.enabled === 1 ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" type="warning" v-perm="'notify:channel:add'" @click="openTest(row)">测试</el-button>
            <el-button size="small" type="danger" v-perm="'notify:channel:del'" @click="onDeleteChannel(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="card-gap">
      <template #header>
        <div class="toolbar">
          <span class="title">发送记录</span>
        </div>
      </template>

      <el-form inline :model="recQuery" @submit.prevent="loadRecords">
        <el-form-item label="渠道">
          <el-select v-model="recQuery.channel_id" clearable placeholder="全部" style="width: 160px">
            <el-option v-for="c in channels" :key="c.id" :label="c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="recQuery.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadRecords">查询</el-button>
          <el-button @click="resetRecQuery">重置</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="records" v-loading="recordsLoading" border>
        <el-table-column prop="title" label="标题" min-width="160" show-overflow-tooltip />
        <el-table-column prop="scene" label="场景" width="100" />
        <el-table-column prop="target" label="接收方" min-width="160" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误" min-width="160" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'failed'"
              size="small"
              type="warning"
              v-perm="'notify:record:resend'"
              @click="onResend(row.id)"
            >
              重发
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="pager"
        layout="total, prev, pager, next, sizes"
        :total="recordsTotal"
        v-model:current-page="recQuery.page"
        v-model:page-size="recQuery.size"
        :page-sizes="[10, 20, 50]"
        @change="loadRecords"
      />
    </el-card>

    <el-dialog v-model="channelVisible" :title="channelId ? '编辑渠道' : '新增渠道'" width="520px">
      <el-form :model="channelForm" label-width="80px">
        <el-form-item label="渠道名">
          <el-input v-model="channelForm.name" :maxlength="64" />
        </el-form-item>
        <el-form-item label="类型" v-if="!channelId">
          <el-select v-model="channelForm.type" style="width: 100%">
            <el-option label="飞书机器人" value="lark" />
            <el-option label="企业微信" value="wecom" />
            <el-option label="钉钉" value="dingtalk" />
            <el-option label="邮件" value="email" />
            <el-option label="Webhook" value="webhook" />
          </el-select>
        </el-form-item>
        <el-form-item label="Webhook">
          <el-input v-model="configInput" placeholder="https://open.feishu.cn/...（仅写入，不返回明文）" />
        </el-form-item>
        <el-form-item label="秘钥">
          <el-input v-model="secretInput" type="password" show-password placeholder="可选" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="channelEnabled" active-value="1" inactive-value="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="channelVisible = false">取消</el-button>
        <el-button type="primary" :loading="channelSaving" @click="onSaveChannel">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="testVisible" :title="`测试发送 - ${testChannel?.name ?? ''}`" width="440px">
      <el-form :model="testForm" label-width="60px">
        <el-form-item label="标题">
          <el-input v-model="testForm.title" />
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="testForm.content" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="testVisible = false">取消</el-button>
        <el-button type="primary" :loading="testing" @click="onTest">发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createChannel,
  deleteChannel,
  listChannels,
  listRecords,
  resendRecord,
  setChannelStatus,
  testChannel as sendChannelTest,
  updateChannel,
} from '../../api/notify'
import type { ChannelOut, NotifyRecordOut, NotifyRecordQuery } from '../../api/types'
import { extractError } from '../../api/http'

const loading = ref(false)
const recordsLoading = ref(false)
const channels = ref<ChannelOut[]>([])
const records = ref<NotifyRecordOut[]>([])
const recordsTotal = ref(0)

const recQuery = reactive<NotifyRecordQuery>({ page: 1, size: 10 })

function formatTime(v: string | null | undefined): string {
  return v ? new Date(v).toLocaleString() : '-'
}

async function loadChannels() {
  loading.value = true
  try {
    channels.value = await listChannels()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    loading.value = false
  }
}

async function loadRecords() {
  recordsLoading.value = true
  try {
    const page = await listRecords(recQuery)
    records.value = page.list
    recordsTotal.value = page.total
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    recordsLoading.value = false
  }
}

function resetRecQuery() {
  recQuery.channel_id = undefined
  recQuery.status = undefined
  recQuery.page = 1
  loadRecords()
}

const channelVisible = ref(false)
const channelSaving = ref(false)
const channelId = ref<number | null>(null)
const channelForm = reactive({ name: '', type: 'lark' })
const configInput = ref('')
const secretInput = ref('')
const channelEnabled = ref('1')

function openChannel(row?: ChannelOut) {
  if (row) {
    channelId.value = row.id
    channelForm.name = row.name
    channelForm.type = row.type
    channelEnabled.value = String(row.enabled)
    const mask = row.config_mask as Record<string, unknown>
    configInput.value = (mask.webhook as string) ?? (mask.url as string) ?? ''
    secretInput.value = ''
  } else {
    channelId.value = null
    channelForm.name = ''
    channelForm.type = 'lark'
    configInput.value = ''
    secretInput.value = ''
    channelEnabled.value = '1'
  }
  channelVisible.value = true
}

async function onSaveChannel() {
  if (channelForm.name.length < 1) {
    ElMessage.warning('请输入渠道名')
    return
  }
  if (!channelId.value && configInput.value.length < 1) {
    ElMessage.warning('请输入 Webhook 地址')
    return
  }
  const config: Record<string, unknown> = {}
  if (configInput.value) config.webhook = configInput.value
  if (secretInput.value) config.secret = secretInput.value
  channelSaving.value = true
  try {
    if (channelId.value) {
      await updateChannel(channelId.value, { name: channelForm.name, config, enabled: Number(channelEnabled.value) })
    } else {
      await createChannel({
        name: channelForm.name,
        type: channelForm.type,
        config,
        enabled: Number(channelEnabled.value),
      })
    }
    ElMessage.success('保存成功')
    channelVisible.value = false
    loadChannels()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    channelSaving.value = false
  }
}

async function toggleChannel(row: ChannelOut) {
  try {
    await setChannelStatus(row.id, { enabled: row.enabled === 1 ? 0 : 1 })
    ElMessage.success('状态已更新')
    loadChannels()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

async function onDeleteChannel(row: ChannelOut) {
  try {
    await ElMessageBox.confirm(`确定删除渠道「${row.name}」吗？`, '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteChannel(row.id)
    ElMessage.success('已删除')
    loadChannels()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

const testVisible = ref(false)
const testing = ref(false)
const testChannel = ref<ChannelOut | null>(null)
const testForm = reactive({ title: 'test', content: 'lark-plat test message' })

function openTest(row: ChannelOut) {
  testChannel.value = row
  testForm.title = 'test'
  testForm.content = 'lark-plat test message'
  testVisible.value = true
}

async function onTest() {
  if (!testChannel.value) return
  testing.value = true
  try {
    await sendChannelTest(testChannel.value.id, testForm)
    ElMessage.success('测试消息已发送')
    testVisible.value = false
    loadRecords()
  } catch (e) {
    ElMessage.error(extractError(e))
  } finally {
    testing.value = false
  }
}

async function onResend(recordId: number) {
  try {
    await resendRecord(recordId)
    ElMessage.success('已重发')
    loadRecords()
  } catch (e) {
    ElMessage.error(extractError(e))
  }
}

onMounted(() => {
  loadChannels()
  loadRecords()
})
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
.card-gap {
  margin-top: 16px;
}
</style>
