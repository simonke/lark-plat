import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import AlertRulesView from '../src/views/monitoring/AlertRulesView.vue'
import { vPerm } from '../src/directives/perm'

vi.mock('../src/api/monitoring', () => ({
  listAlertRules: vi.fn(),
  createAlertRule: vi.fn(),
  updateAlertRule: vi.fn(),
  setRuleStatus: vi.fn(),
  deleteAlertRule: vi.fn(),
}))

import * as monApi from '../src/api/monitoring'
import { useAuthStore } from '../src/stores/auth'
import { ElMessage } from 'element-plus'

vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)

function makeWrapper() {
  return mount(AlertRulesView, {
    global: {
      plugins: [ElementPlus],
      directives: { perm: vPerm },
    },
  })
}

const ruleRow = {
  id: 'r1',
  name: 'high-cpu',
  description: null,
  enabled: true,
  event_source: 'agent',
  event_kind: 'metric',
  metric_name: 'cpu_usage_percent',
  condition_operator: '>',
  condition_threshold: 90,
  condition_duration_seconds: 60,
  scope_type: 'host',
  scope_ids: ['h1'],
  level: 'warning',
  cooldown_seconds: 300,
  converge_sec: 0,
  escalation_enabled: true,
  escalation_after_seconds: 600,
  escalation_severity: 'warning',
  escalate_levels: ['warning', 'critical'],
  notify_scene: 'alert',
  notify_channel_ids: [],
  created_by: 1,
  created_at: '2026-09-09T11:00:00+00:00',
  updated_at: '2026-09-09T11:00:00+00:00',
}

describe('AlertRulesView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loads rules on mount and renders rows', async () => {
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

    vi.mocked(monApi.listAlertRules).mockResolvedValue({
      list: [ruleRow],
      total: 1,
      page: 1,
      size: 10,
    })

    const wrapper = makeWrapper()
    await flushPromises()

    expect(monApi.listAlertRules).toHaveBeenCalled()
    expect(wrapper.text()).toContain('high-cpu')
    expect(wrapper.text()).toContain('> 90')
    wrapper.unmount()
  })

  it('opens create dialog and creates a rule', async () => {
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

    vi.mocked(monApi.listAlertRules).mockResolvedValue({ list: [], total: 0, page: 1, size: 10 })
    vi.mocked(monApi.createAlertRule).mockResolvedValue({ ...ruleRow, id: 'new1' })

    const wrapper = makeWrapper()
    await flushPromises()

    const addBtn = wrapper.findAll('button').find((b) => b.text().includes('新增规则'))
    expect(addBtn).toBeTruthy()
    await addBtn!.trigger('click')
    await flushPromises()

    const dialogInput = wrapper.find('.el-dialog .el-form input')
    await dialogInput.setValue('disk-full')
    const saveBtn = wrapper.findAll('button').find((b) => b.text() === '保存')
    expect(saveBtn).toBeTruthy()
    await saveBtn!.trigger('click')
    await flushPromises()

    expect(monApi.createAlertRule).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('deletes a rule after confirmation', async () => {
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

    vi.mocked(monApi.listAlertRules).mockResolvedValue({
      list: [ruleRow],
      total: 1,
      page: 1,
      size: 10,
    })

    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const wrapper = makeWrapper()
    await flushPromises()

    expect(wrapper.text()).toContain('删除')
    wrapper.unmount()
  })

  it('toggles rule status via the status endpoint', async () => {
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

    vi.mocked(monApi.listAlertRules).mockResolvedValue({
      list: [ruleRow],
      total: 1,
      page: 1,
      size: 10,
    })
    vi.mocked(monApi.setRuleStatus).mockResolvedValue()

    const wrapper = makeWrapper()
    await flushPromises()

    const toggleBtn = wrapper.findAll('button').find((b) => b.text().includes('停用'))
    expect(toggleBtn).toBeTruthy()
    await toggleBtn!.trigger('click')
    await flushPromises()

    expect(monApi.updateAlertRule).not.toHaveBeenCalled()
    expect(monApi.setRuleStatus).toHaveBeenCalledWith('r1', false)
    wrapper.unmount()
  })
})
