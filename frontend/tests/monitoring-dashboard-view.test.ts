import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { vPerm } from '../src/directives/perm'
import { useAuthStore } from '../src/stores/auth'

vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}))

vi.mock('../src/api/monitoring', () => ({
  getMetrics: vi.fn(),
  listAlerts: vi.fn(),
  getMonitoringWsToken: vi.fn(),
}))

import * as monApi from '../src/api/monitoring'
import MonitoringDashboardView from '../src/views/monitoring/MonitoringDashboardView.vue'

class FakeWebSocket {
  static OPEN = 1
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(public url: string) {}
  send(): void {}
  close(): void {}
}

function alertRow(id: number, status: string, severity: string) {
  return { id, status, severity, source: 'agent', entity: { entity_id: String(id) } }
}

function setAdmin() {
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
}

function mountView() {
  return mount(MonitoringDashboardView, {
    global: { plugins: [ElementPlus], directives: { perm: vPerm } },
  })
}

describe('MonitoringDashboardView alertStats (item6 同源派生)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.mocked(monApi.getMonitoringWsToken).mockRejectedValue(new Error('no ws in unit test'))
    vi.mocked(monApi.getMetrics).mockResolvedValue({
      agg: null,
      points: [],
      total: 0,
      page: 1,
      size: 10,
    } as never)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('derives 触发中/严重/警告 from the /monitor/alerts first page (same source)', async () => {
    setAdmin()
    vi.mocked(monApi.listAlerts).mockResolvedValue({
      list: [
        alertRow(1, 'firing', 'critical'),
        alertRow(2, 'firing', 'warning'),
        alertRow(3, 'resolved', 'critical'),
        alertRow(4, 'pending', 'info'),
      ],
      total: 4,
      page: 1,
      size: 10,
    } as never)

    const wrapper = mountView()
    await flushPromises()

    expect(monApi.listAlerts).toHaveBeenCalledWith({ size: 10 })
    const values = wrapper.findAll('.stat-value').map((n) => n.text())
    expect(values.slice(0, 3)).toEqual(['2', '2', '1'])
    wrapper.unmount()
  })

  it('计数随第 1 页（size=10）派生，不等于全局 total，且标签为「最近」概览语义', async () => {
    setAdmin()
    const tenFiring = Array.from({ length: 10 }, (_, i) => alertRow(i + 1, 'firing', 'warning'))
    vi.mocked(monApi.listAlerts).mockResolvedValue({
      list: tenFiring,
      total: 50,
      page: 1,
      size: 10,
    } as never)

    const wrapper = mountView()
    await flushPromises()

    const values = wrapper.findAll('.stat-value').map((n) => n.text())
    expect(values[0]).toBe('10')
    expect(values[0]).not.toBe('50')
    expect(wrapper.text()).toContain('触发中告警（最近）')
    wrapper.unmount()
  })
})
