import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  setScheduleStatus,
  runNow,
  listScheduleRuns,
  retryScheduleRun,
} from '../src/api/schedule'
import {
  getDashboardStats,
  getTaskTrend,
  getRecentTasks,
  getRecentApprovals,
} from '../src/api/dashboard'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

function ok(data: unknown) {
  return { data: { code: 0, message: 'ok', data } }
}

describe('Schedule API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists schedules with name/enabled filters and pagination', async () => {
    const page = { list: [{ id: 1, name: 's1' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listSchedules({ name: 's1', enabled: 1, page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/schedules', {
      params: { name: 's1', enabled: 1, page: 1, size: 10 },
    })
    expect(result).toEqual(page)
  })

  it('omits params when no query given', async () => {
    vi.mocked(http.get).mockResolvedValue(ok({ list: [], total: 0, page: 1, size: 10 }))
    await listSchedules()
    expect(http.get).toHaveBeenCalledWith('/schedules', { params: undefined })
  })

  it('creates a schedule with cron payload', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 7 }))
    const payload = {
      name: 'backup',
      kind: 'command' as const,
      command: 'tar czf /data/backup.tar /data',
      params: null as null,
      trigger_type: 'cron' as const,
      cron_expr: '0 2 * * *',
      timezone: 'Asia/Shanghai',
      interval_sec: null as null,
      target_host_ids: [1, 2],
      timeout_sec: 300,
      retry: 1,
      concurrency_limit: 10,
      enabled: 1,
    }
    const result = await createSchedule(payload)
    expect(http.post).toHaveBeenCalledWith('/schedules', payload)
    expect(result).toEqual({ id: 7 })
  })

  it('creates a schedule with interval trigger', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 8 }))
    const payload = {
      name: 'health-check',
      kind: 'script' as const,
      script_id: 3,
      command: null as null,
      params: { env: 'prod' },
      trigger_type: 'interval' as const,
      cron_expr: null as null,
      timezone: 'Asia/Shanghai',
      interval_sec: 3600,
      target_host_ids: [5],
      timeout_sec: 60,
      enabled: 1,
    }
    await createSchedule(payload)
    expect(http.post).toHaveBeenCalledWith('/schedules', payload)
  })

  it('updates a schedule (patch semantics)', async () => {
    vi.mocked(http.put).mockResolvedValue(ok(null))
    await updateSchedule(7, { name: 'backup-v2', cron_expr: '30 2 * * *' })
    expect(http.put).toHaveBeenCalledWith('/schedules/7', { name: 'backup-v2', cron_expr: '30 2 * * *' })
  })

  it('deletes a schedule', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok(null))
    await deleteSchedule(7)
    expect(http.delete).toHaveBeenCalledWith('/schedules/7')
  })

  it('sets schedule status', async () => {
    vi.mocked(http.put).mockResolvedValue(ok(null))
    await setScheduleStatus(7, 0)
    expect(http.put).toHaveBeenCalledWith('/schedules/7/status', { enabled: 0 })
  })

  it('triggers run-now (direct dispatch)', async () => {
    vi.mocked(http.post).mockResolvedValue(
      ok({ run_id: 11, task_id: 22, status: 'running', approve_required: false, approval_id: null, sensitive_flag: false }),
    )
    const result = await runNow(7)
    expect(http.post).toHaveBeenCalledWith('/schedules/7/run-now')
    expect(result.status).toBe('running')
    expect(result.approve_required).toBe(false)
  })

  it('triggers run-now (sensitive => awaiting approval)', async () => {
    vi.mocked(http.post).mockResolvedValue(
      ok({ run_id: 11, task_id: 22, status: 'awaiting_approval', approve_required: true, approval_id: 99, sensitive_flag: true }),
    )
    const result = await runNow(7)
    expect(result.status).toBe('awaiting_approval')
    expect(result.approve_required).toBe(true)
    expect(result.approval_id).toBe(99)
    expect(result.sensitive_flag).toBe(true)
  })

  it('lists schedule runs with pagination', async () => {
    const page = { list: [{ id: 1, schedule_task_id: 7, run_no: 'R-7-1' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listScheduleRuns(7, { page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/schedules/7/runs', { params: { page: 1, size: 10 } })
    expect(result).toEqual(page)
  })

  it('retries a failed run (direct dispatch, no approval fields)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ run_id: 11, task_id: 22, status: 'running' }))
    const result = await retryScheduleRun(7, 1)
    expect(http.post).toHaveBeenCalledWith('/schedules/7/runs/1/retry')
    expect(result.task_id).toBe(22)
    expect(result.approve_required).toBeUndefined()
  })

  it('retries a failed run (sensitive => awaiting approval)', async () => {
    vi.mocked(http.post).mockResolvedValue(
      ok({ run_id: 11, task_id: 22, status: 'awaiting_approval', approve_required: true, approval_id: 99, sensitive_flag: true }),
    )
    const result = await retryScheduleRun(7, 1)
    expect(result.approve_required).toBe(true)
    expect(result.approval_id).toBe(99)
  })
})

describe('Dashboard API', () => {
  beforeEach(() => vi.clearAllMocks())

  it('fetches dashboard stats', async () => {
    const stats = { host_total: 12, host_online: 9, tasks_running: 3, today_tasks: 20, today_success: 18, pending_approvals: 2 }
    vi.mocked(http.get).mockResolvedValue(ok(stats))
    const result = await getDashboardStats()
    expect(http.get).toHaveBeenCalledWith('/dashboard/stats')
    expect(result.host_total).toBe(12)
  })

  it('fetches task trend with days param (default 7)', async () => {
    vi.mocked(http.get).mockResolvedValue(ok([{ date: '2026-09-01', total: 5, success: 4, failed: 1 }]))
    const result = await getTaskTrend()
    expect(http.get).toHaveBeenCalledWith('/dashboard/task-trend', { params: { days: 7 } })
    expect(result).toHaveLength(1)

    vi.mocked(http.get).mockResolvedValue(ok([]))
    await getTaskTrend(30)
    expect(http.get).toHaveBeenCalledWith('/dashboard/task-trend', { params: { days: 30 } })
  })

  it('fetches recent tasks', async () => {
    const tasks = [{ id: 1, task_no: 'T0001', name: 't', status: 'success', kind: 'command', created_at: '2026-09-06T01:00:00+00:00' }]
    vi.mocked(http.get).mockResolvedValue(ok(tasks))
    const result = await getRecentTasks()
    expect(http.get).toHaveBeenCalledWith('/dashboard/recent-tasks')
    expect(result).toEqual(tasks)
  })

  it('fetches recent approvals', async () => {
    const approvals = [{ id: 1, request_no: 'AP-1', title: 'a', status: 'pending', created_at: '2026-09-06T01:00:00+00:00' }]
    vi.mocked(http.get).mockResolvedValue(ok(approvals))
    const result = await getRecentApprovals()
    expect(http.get).toHaveBeenCalledWith('/dashboard/recent-approvals')
    expect(result).toEqual(approvals)
  })
})