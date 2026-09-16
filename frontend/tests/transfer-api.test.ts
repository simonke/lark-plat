import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  uploadPackage,
  deletePackage,
  getPackage,
  getPackages,
  createTransferTask,
  getTransferTasks,
  getMyTransferTasks,
  getTransferTask,
  getTransferStats,
  stopTransferTask,
  retryTransferHost,
  getTransferLogs,
  getTransferWsToken,
} from '../src/api/transfer'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}))

describe('Transfer API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should upload a package as multipart form data', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { code: 0, message: 'ok', data: { package_id: 7, items: [{ path: 'a.txt', size: 3, sha256: 'x' }] } },
    })
    const result = await uploadPackage([new File(['abc'], 'a.txt')], 'demo')
    expect(http.post).toHaveBeenCalledWith(
      '/transfer/packages',
      expect.any(FormData),
    )
    expect(result.package_id).toBe(7)
    expect(result.items).toHaveLength(1)
  })

  it('should list packages with name filter', async () => {
    const page = { list: [{ id: 7, name: 'demo', file_count: 1, total_size: 3, created_by: 1, created_at: 't' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: page } })
    const result = await getPackages({ name: 'demo' })
    expect(http.get).toHaveBeenCalledWith('/transfer/packages', { params: { name: 'demo' } })
    expect(result).toEqual(page)
  })

  it('should get package detail and delete it', async () => {
    const detail = { id: 7, name: 'demo', file_count: 1, total_size: 3, created_by: 1, created_at: 't', items: [{ path: 'a.txt', size: 3, sha256: 'x' }] }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: detail } })
    const got = await getPackage(7)
    expect(http.get).toHaveBeenCalledWith('/transfer/packages/7')
    expect(got.items).toHaveLength(1)

    vi.mocked(http.delete).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await deletePackage(7)
    expect(http.delete).toHaveBeenCalledWith('/transfer/packages/7')
  })

  it('should create a transfer task with 0|1 booleans', async () => {
    vi.mocked(http.post).mockResolvedValue({
      data: { code: 0, message: 'ok', data: { id: 12, task_no: 'TF-20260908-001', status: 'processing', pending: 3 } },
    })
    const result = await createTransferTask({
      mode: 'push',
      package_id: 7,
      target_path: '/opt/pkg/app',
      host_ids: [1, 2, 3],
      overwrite: 0,
      verify: 1,
    })
    expect(http.post).toHaveBeenCalledWith('/transfer/tasks', {
      mode: 'push',
      package_id: 7,
      target_path: '/opt/pkg/app',
      host_ids: [1, 2, 3],
      overwrite: 0,
      verify: 1,
    })
    expect(result.status).toBe('processing')
  })

  it('should list and get transfer tasks', async () => {
    const page = { list: [{ id: 12, task_no: 'TF-1', mode: 'push', status: 'processing' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: page } })
    const tasks = await getTransferTasks({ mode: 'push' })
    expect(http.get).toHaveBeenCalledWith('/transfer/tasks', { params: { mode: 'push' } })
    expect(tasks.list).toHaveLength(1)

    const detail = { id: 12, task_no: 'TF-1', mode: 'push', status: 'processing', hosts: [], stats: { total: 3, pending: 3, transferring: 0, verifying: 0, verify_failed: 0, success: 0, failed: 0 } }
    vi.mocked(http.get).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: detail } })
    const got = await getTransferTask(12)
    expect(http.get).toHaveBeenCalledWith('/transfer/tasks/12')
    expect(got.stats).toBeDefined()
  })

  it('should list tasks via mine endpoint for viewer log entry', async () => {
    const page = { list: [{ id: 1, task_no: 'TF-M', mode: 'pull', status: 'success', host_ids: { ids: [9] }, hosts: [{ id: 8, hostname: 'agent-008' }] }], total: 1, page: 1, size: 100 }
    vi.mocked(http.get).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: page } })
    const result = await getMyTransferTasks()
    expect(http.get).toHaveBeenCalledWith('/transfer/tasks/mine', { params: undefined })
    expect(result.list[0].task_no).toBe('TF-M')
  })

  it('should fetch stats, stop, retry, logs and ws-token', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { total: 3, pending: 0, transferring: 1, verifying: 0, verify_failed: 1, success: 1, failed: 1 } } })
    const stats = await getTransferStats(12)
    expect(http.get).toHaveBeenCalledWith('/transfer/tasks/12/stats')
    expect(stats.verify_failed).toBe(1)

    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })
    await stopTransferTask(12)
    expect(http.post).toHaveBeenCalledWith('/transfer/tasks/12/stop')
    await retryTransferHost(12, 99)
    expect(http.post).toHaveBeenCalledWith('/transfer/tasks/12/hosts/99/retry')

    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { list: [], next_seq: 5 } } })
    const logs = await getTransferLogs(12, 99, 3, 200)
    expect(http.get).toHaveBeenCalledWith('/transfer/tasks/12/hosts/99/logs', { params: { after_seq: 3, size: 200 } })
    expect(logs.next_seq).toBe(5)

    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { token: 'jwt' } } })
    const token = await getTransferWsToken(12, 99)
    expect(http.get).toHaveBeenCalledWith('/transfer/tasks/12/hosts/99/ws-token')
    expect(token).toBe('jwt')
  })
})