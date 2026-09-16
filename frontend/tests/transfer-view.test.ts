import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import TransferView from '../src/views/transfer/TransferView.vue'
import { vPerm } from '../src/directives/perm'

vi.mock('../src/api/transfer', () => ({
  uploadPackage: vi.fn(),
  getPackages: vi.fn(),
  getPackage: vi.fn(),
  deletePackage: vi.fn(),
  createTransferTask: vi.fn(),
  getTransferTasks: vi.fn(),
  getMyTransferTasks: vi.fn(),
  getTransferTask: vi.fn(),
  stopTransferTask: vi.fn(),
  retryTransferHost: vi.fn(),
}))

vi.mock('../src/api/assets', () => ({
  getHosts: vi.fn(),
}))

vi.mock('../src/composables/useTransferRealtimeLog', () => ({
  useTransferRealtimeLog: () => ({
    lines: { value: [] as { seq: number; level: string; content: string }[] },
    connected: { value: false },
    start: vi.fn(),
    stop: vi.fn(),
  }),
}))

import * as transApi from '../src/api/transfer'
import * as assetsApi from '../src/api/assets'
import { useAuthStore } from '../src/stores/auth'
import { ElMessage } from 'element-plus'

vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)

function makeWrapper() {
  return mount(TransferView, {
    global: {
      plugins: [ElementPlus],
      directives: { perm: vPerm },
    },
  })
}

const pkgRow = { id: 7, name: 'demo', file_count: 2, total_size: 1024, created_by: 1, created_at: '2026-09-13T10:00:00Z' }
const taskRow = {
  id: 12,
  task_no: 'TF-20260913-001',
  mode: 'push',
  package_id: 7,
  source_host_id: null,
  source_host_path: null,
  target_path: '/opt/pkg/app',
  host_ids: { ids: [1, 2] },
  overwrite: 0,
  verify: 1,
  limit_mbps: null,
  status: 'processing',
  created_by: 1,
  created_at: '2026-09-13T10:00:00Z',
  started_at: null,
  finished_at: null,
}

describe('TransferView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads packages on mount and renders rows', async () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'admin',
      real_name: 'Admin',
      roles: [],
      permissions: [],
      visible_group_ids: [],
      is_admin: true,
    }
    store.loaded = true

    vi.mocked(transApi.getPackages).mockResolvedValue({
      list: [pkgRow],
      total: 1,
      page: 1,
      size: 10,
    })

    const wrapper = makeWrapper()
    await flushPromises()

    expect(transApi.getPackages).toHaveBeenCalled()
    expect(wrapper.text()).toContain('demo')
    expect(wrapper.text()).toContain('文件包管理')
  })

  it('switches to task tab and loads tasks with retry button for failed tasks', async () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'admin',
      real_name: 'Admin',
      roles: [],
      permissions: [],
      visible_group_ids: [],
      is_admin: true,
    }
    store.loaded = true

    vi.mocked(transApi.getPackages).mockResolvedValue({ list: [], total: 0, page: 1, size: 10 })
    vi.mocked(transApi.getTransferTasks).mockResolvedValue({ list: [taskRow], total: 1, page: 1, size: 10 })

    const wrapper = makeWrapper()
    await flushPromises()

    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    expect(transApi.getTransferTasks).toHaveBeenCalled()
    expect(wrapper.text()).toContain('TF-20260913-001')
    expect(wrapper.text()).toContain('停止')
  })

  it('viewer without transfer:task:list sees packages and logs tabs, no tasks tab', async () => {
    const store = useAuthStore()
    store.user = {
      id: 2,
      username: 'viewer',
      real_name: 'Viewer',
      roles: ['viewer'],
      permissions: ['transfer:package:list', 'transfer:task:log'],
      visible_group_ids: [],
      is_admin: false,
    }
    store.loaded = true

    vi.mocked(transApi.getPackages).mockResolvedValue({ list: [pkgRow], total: 1, page: 1, size: 10 })

    const wrapper = makeWrapper()
    await flushPromises()

    expect(transApi.getPackages).toHaveBeenCalled()
    expect(wrapper.findAll('[role="tab"]')).toHaveLength(2)
    expect(wrapper.findAll('[role="tab"]')[0].text()).toContain('包管理')
    expect(wrapper.findAll('[role="tab"]')[1].text()).toContain('传输日志')
    expect(wrapper.text()).not.toContain('任务列表')
    expect(transApi.getTransferTasks).not.toHaveBeenCalled()
  })

  it('viewer logs tab loads my tasks and can open log dialog for a host', async () => {
    const store = useAuthStore()
    store.user = {
      id: 2,
      username: 'viewer',
      real_name: 'Viewer',
      roles: ['viewer'],
      permissions: ['transfer:package:list', 'transfer:task:log'],
      visible_group_ids: [],
      is_admin: false,
    }
    store.loaded = true

    vi.mocked(transApi.getPackages).mockResolvedValue({ list: [], total: 0, page: 1, size: 10 })
    vi.mocked(transApi.getMyTransferTasks).mockResolvedValue({
      list: [
        {
          ...taskRow,
          id: 50,
          task_no: 'TF-LOG',
          host_ids: { ids: [1, 2] },
          hosts: [
            { id: 26, hostname: 'agent-001' },
            { id: 27, hostname: 'agent-002' },
          ],
        },
      ],
      total: 1,
      page: 1,
      size: 10,
    })

    const wrapper = makeWrapper()
    await flushPromises()

    // switch to logs tab (index 1)
    await wrapper.findAll('[role="tab"]')[1].trigger('click')
    await flushPromises()

    expect(transApi.getMyTransferTasks).toHaveBeenCalled()
    expect(wrapper.text()).toContain('TF-LOG')
    expect(wrapper.text()).toContain('agent-001 日志')
    expect(wrapper.text()).toContain('agent-002 日志')
    // transfer_host_id uses TransferHost ROW ids from hosts[], never the asset ids in host_ids
    expect(wrapper.text()).not.toContain('#1 日志')
    expect(wrapper.text()).not.toContain('#2 日志')

    // click first host log button -> log dialog opens with row id as task id + hostname label
    const logBtn = wrapper.findAll('.host-log-btn').find((b) => b.text().includes('agent-001'))
    await logBtn!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('实时日志')
    expect(wrapper.text()).toContain('agent-001')
    expect(wrapper.text()).toContain('transfer_host_id=26')
  })

  it('operator with transfer:task:list sees both tabs', async () => {
    const store = useAuthStore()
    store.user = {
      id: 3,
      username: 'operator',
      real_name: 'Operator',
      roles: ['operator'],
      permissions: ['transfer:package:list', 'transfer:task:list'],
      visible_group_ids: [],
      is_admin: false,
    }
    store.loaded = true

    vi.mocked(transApi.getPackages).mockResolvedValue({ list: [], total: 0, page: 1, size: 10 })

    const wrapper = makeWrapper()
    await flushPromises()

    expect(wrapper.findAll('[role="tab"]')).toHaveLength(2)
    expect(wrapper.findAll('[role="tab"]')[1].text()).toContain('任务列表')
    expect(wrapper.text()).not.toContain('传输日志')
  })

  it('opens package detail dialog', async () => {
    const store = useAuthStore()
    store.user = {
      id: 1,
      username: 'admin',
      real_name: 'Admin',
      roles: [],
      permissions: [],
      visible_group_ids: [],
      is_admin: true,
    }
    store.loaded = true

    vi.mocked(transApi.getPackages).mockResolvedValue({ list: [pkgRow], total: 1, page: 1, size: 10 })
    vi.mocked(transApi.getPackage).mockResolvedValue({
      ...pkgRow,
      items: [{ path: 'a.txt', size: 1024, sha256: 'abc' }],
    })

    const wrapper = makeWrapper()
    await flushPromises()

    const btn = wrapper.findAll('button').find((b) => b.text().includes('详情'))
    await btn!.trigger('click')
    await flushPromises()

    expect(transApi.getPackage).toHaveBeenCalledWith(7)
    expect(wrapper.text()).toContain('a.txt')
  })
})