import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getTasks, createTask, getTask, getTaskStats, stopTask, retryTask, getLogs, getWsToken } from '../src/api/exec'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn()
  }
}))

describe('Exec API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should get tasks list with filters and pagination', async () => {
    const mockPage = { list: [{ id: 1, task_no: 'T0001' }], total: 1, page: 2, size: 10 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockPage } })

    const result = await getTasks({ task_no: 'T0001', status: 'running', kind: 'command', page: 2, size: 10 })

    expect(http.get).toHaveBeenCalledWith('/exec/tasks', {
      params: { task_no: 'T0001', status: 'running', kind: 'command', page: 2, size: 10 }
    })
    expect(result).toEqual(mockPage)
  })

  it('should create task with command payload', async () => {
    const payload = {
      name: 't1',
      kind: 'command' as const,
      command: 'uptime',
      target_host_ids: [1, 2],
      mode: 'batch',
      timeout_sec: 300,
      retry: 0
    }
    const detail = { id: 5, hosts: [], approval_status: null }
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: detail } })

    const result = await createTask(payload)

    expect(http.post).toHaveBeenCalledWith('/exec/tasks', payload)
    expect(result).toEqual(detail)
  })

  it('should get task detail by id', async () => {
    const detail = { id: 5, hosts: [{ id: 51, hostname: 'h1' }], approval_status: null }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: detail } })

    const result = await getTask(5)

    expect(http.get).toHaveBeenCalledWith('/exec/tasks/5')
    expect(result).toEqual(detail)
  })

  it('should get task stats', async () => {
    const stats = { total: 10, pending: 1, running: 2, success: 5, failed: 1, timed_out: 1, canceled: 0 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: stats } })

    const result = await getTaskStats(5)

    expect(http.get).toHaveBeenCalledWith('/exec/tasks/5/stats')
    expect(result).toEqual(stats)
  })

  it('should stop task via REST only', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

    await stopTask(5)

    expect(http.post).toHaveBeenCalledWith('/exec/tasks/5/stop')
  })

  it('should retry task via REST only', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

    await retryTask(5)

    expect(http.post).toHaveBeenCalledWith('/exec/tasks/5/retry')
  })

  it('should fetch logs with after_seq cursor and page size', async () => {
    const logPage = { list: [{ seq: 1, level: 'info', content: 'start', created_at: '2026-08-25 10:00:00' }], next_seq: 1 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: logPage } })

    const result = await getLogs(5, 51, 0, 200)

    expect(http.get).toHaveBeenCalledWith('/exec/tasks/5/hosts/51/logs', {
      params: { after_seq: 0, size: 200 }
    })
    expect(result.next_seq).toBe(1)
  })

  it('should advance the cursor: next after_seq equals previous next_seq (incremental replay)', async () => {
    const first = { list: [{ seq: 1 }, { seq: 2 }], next_seq: 2 }
    vi.mocked(http.get).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: first } })
    const second = { list: [{ seq: 3 }], next_seq: 3 }
    vi.mocked(http.get).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: second } })

    const p1 = await getLogs(5, 51, 0)
    const p2 = await getLogs(5, 51, p1.next_seq)

    expect(vi.mocked(http.get)).toHaveBeenNthCalledWith(1, '/exec/tasks/5/hosts/51/logs', {
      params: { after_seq: 0, size: 200 }
    })
    expect(vi.mocked(http.get)).toHaveBeenNthCalledWith(2, '/exec/tasks/5/hosts/51/logs', {
      params: { after_seq: 2, size: 200 }
    })
    expect(p2.list[0].seq).toBe(3)
  })

  it('should exchange ws-token bound to task_host', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { token: 'jwt-abc' } } })

    const token = await getWsToken(5, 51)

    expect(http.get).toHaveBeenCalledWith('/exec/tasks/5/hosts/51/ws-token')
    expect(token).toBe('jwt-abc')
  })
})
