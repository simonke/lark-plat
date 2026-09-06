import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import SchedulesView from '../src/views/schedules/SchedulesView.vue'

vi.mock('../src/api/schedule', () => ({
  listSchedules: vi.fn(),
  createSchedule: vi.fn(),
  updateSchedule: vi.fn(),
  deleteSchedule: vi.fn(),
  setScheduleStatus: vi.fn(),
  runNow: vi.fn(),
  listScheduleRuns: vi.fn(),
  retryScheduleRun: vi.fn(),
}))

vi.mock('../src/api/scripts', () => ({
  getScripts: vi.fn(),
}))

vi.mock('../src/api/assets', () => ({
  getHosts: vi.fn(),
}))

import * as scheduleApi from '../src/api/schedule'
import * as scriptsApi from '../src/api/scripts'
import * as assetsApi from '../src/api/assets'
import { useAuthStore } from '../src/stores/auth'
import { ElMessage } from 'element-plus'

vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)

function makeWrapper() {
  return mount(SchedulesView, {
    global: {
      plugins: [ElementPlus],
    },
  })
}

describe('SchedulesView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads schedules list on mount and renders rows', async () => {
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

    vi.mocked(scheduleApi.listSchedules).mockResolvedValue({
      list: [
        {
          id: 1,
          name: 'backup',
          kind: 'command',
          script_id: null,
          command: 'tar czf /tmp/b.tar /data',
          params: null,
          trigger_type: 'cron',
          cron_expr: '0 2 * * *',
          timezone: 'Asia/Shanghai',
          interval_sec: null,
          target_host_ids: { ids: [1] },
          timeout_sec: 300,
          retry: 0,
          concurrency_limit: 10,
          enabled: 1,
          created_by: 1,
          created_at: '2026-09-06T01:00:00+00:00',
        },
      ],
      total: 1,
      page: 1,
      size: 10,
    })

    const wrapper = makeWrapper()
    await flushPromises()

    expect(scheduleApi.listSchedules).toHaveBeenCalled()
    expect(wrapper.text()).toContain('backup')
    expect(wrapper.text()).toContain('cron')
    wrapper.unmount()
  })

  it('triggers run-now on button click', async () => {
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

    vi.mocked(scheduleApi.listSchedules).mockResolvedValue({
      list: [
        {
          id: 3,
          name: 'hc',
          kind: 'script',
          script_id: 2,
          command: null,
          params: null,
          trigger_type: 'interval',
          cron_expr: null,
          timezone: 'Asia/Shanghai',
          interval_sec: 60,
          target_host_ids: { ids: [1] },
          timeout_sec: 60,
          retry: 0,
          concurrency_limit: 5,
          enabled: 1,
          created_by: 1,
          created_at: '2026-09-06T01:00:00+00:00',
        },
      ],
      total: 1,
      page: 1,
      size: 10,
    })
    vi.mocked(scheduleApi.runNow).mockResolvedValue({ run_id: 9, task_id: 10, status: 'running' })

    const wrapper = makeWrapper()
    await flushPromises()

    const buttons = wrapper.findAll('button').map((b) => b.text())
    const runBtn = wrapper.findAll('button').find((b) => b.text().includes('立即执行'))
    expect(runBtn).toBeTruthy()
    expect(buttons).toContain('立即执行')
    await runBtn!.trigger('click')

    expect(scheduleApi.runNow).toHaveBeenCalledWith(3)
    wrapper.unmount()
  })
})