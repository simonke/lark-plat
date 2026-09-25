import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listWorkflows,
  createWorkflow,
  getWorkflow,
  updateWorkflow,
  deleteWorkflow,
  listWorkflowVersions,
  createWorkflowVersion,
  rollbackWorkflow,
  runWorkflow,
  listWorkflowRuns,
  getWorkflowRun,
  getWorkflowRunWsToken,
  cancelWorkflowRun,
  retryWorkflowRun,
} from '../src/api/workflow'
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

const DEF = { nodes: [{ key: 'a', type: 'sleep', config: { seconds: 1 }, depends_on: [] }] }

describe('workflow Playbook API (P3-4)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists workflows with query params (Page key = list)', async () => {
    const page = { list: [{ id: 1, name: 'wf1', current_version: 1 }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listWorkflows({ name: 'wf', enabled: 1, page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/workflows', {
      params: { name: 'wf', enabled: 1, page: 1, size: 10 },
    })
    expect(result).toEqual(page)
  })

  it('creates a workflow (returns id/name/current_version)', async () => {
    const row = { id: 5, name: 'wf1', description: '', current_version: 1, enabled: 1, created_by: 1, created_at: 't', updated_at: 't', definition: DEF }
    vi.mocked(http.post).mockResolvedValue(ok(row))
    const result = await createWorkflow({ name: 'wf1', description: '', definition: DEF })
    expect(http.post).toHaveBeenCalledWith('/workflows', { name: 'wf1', description: '', definition: DEF })
    expect(result.id).toBe(5)
    expect(result.current_version).toBe(1)
  })

  it('gets a workflow detail (inlines current_version + definition)', async () => {
    const row = { id: 5, name: 'wf1', description: '', current_version: 2, enabled: 1, created_by: 1, created_at: 't', updated_at: 't', definition: DEF }
    vi.mocked(http.get).mockResolvedValue(ok(row))
    const result = await getWorkflow(5)
    expect(http.get).toHaveBeenCalledWith('/workflows/5')
    expect(result.definition).toEqual(DEF)
  })

  it('updates a workflow', async () => {
    const row = { id: 5, name: 'wf2', description: 'd', current_version: 2, enabled: 0, created_by: 1, created_at: 't', updated_at: 't', definition: DEF }
    vi.mocked(http.put).mockResolvedValue(ok(row))
    const result = await updateWorkflow(5, { name: 'wf2', description: 'd', enabled: 0 })
    expect(http.put).toHaveBeenCalledWith('/workflows/5', { name: 'wf2', description: 'd', enabled: 0 })
    expect(result.enabled).toBe(0)
  })

  it('deletes a workflow', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok(null))
    await deleteWorkflow(5)
    expect(http.delete).toHaveBeenCalledWith('/workflows/5')
  })

  it('lists versions ({list,total} envelope)', async () => {
    const res = { list: [{ id: 1, workflow_id: 5, version: 1, definition: DEF, editor_id: 1, created_at: 't' }], total: 1 }
    vi.mocked(http.get).mockResolvedValue(ok(res))
    const result = await listWorkflowVersions(5)
    expect(http.get).toHaveBeenCalledWith('/workflows/5/versions')
    expect(result.total).toBe(1)
    expect(result.list[0].version).toBe(1)
  })

  it('creates a version', async () => {
    const row = { id: 2, workflow_id: 5, version: 2, definition: DEF, editor_id: 1, created_at: 't' }
    vi.mocked(http.post).mockResolvedValue(ok(row))
    const result = await createWorkflowVersion(5, { definition: DEF, change_log: 'v2' })
    expect(http.post).toHaveBeenCalledWith('/workflows/5/versions', { definition: DEF, change_log: 'v2' })
    expect(result.version).toBe(2)
  })

  it('rolls back to a version', async () => {
    const row = { id: 5, name: 'wf1', description: '', current_version: 1, enabled: 1, created_by: 1, created_at: 't', updated_at: 't', definition: DEF }
    vi.mocked(http.post).mockResolvedValue(ok(row))
    const result = await rollbackWorkflow(5, 1)
    expect(http.post).toHaveBeenCalledWith('/workflows/5/rollback', { version: 1 })
    expect(result.current_version).toBe(1)
  })

  it('runs a workflow with Idempotency-Key header -> {run_id}', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ run_id: 9 }))
    const result = await runWorkflow(5, { trigger_type: 'manual' }, 'key-1')
    expect(http.post).toHaveBeenCalledWith(
      '/workflows/5/run',
      { trigger_type: 'manual' },
      { headers: { 'Idempotency-Key': 'key-1' } },
    )
    expect(result.run_id).toBe(9)
  })

  it('runs a workflow without an idempotency key', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ run_id: 10 }))
    await runWorkflow(5)
    expect(http.post).toHaveBeenCalledWith('/workflows/5/run', {}, { headers: {} })
  })

  it('lists runs (Page envelope)', async () => {
    const page = { list: [{ id: 9, workflow_id: 5, status: 'pending' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listWorkflowRuns({ workflow_id: 5, status: 'pending', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/workflow-runs', {
      params: { workflow_id: 5, status: 'pending', page: 1, size: 10 },
    })
    expect(result.list[0].status).toBe('pending')
  })

  it('gets a run detail ({run, nodes[]})', async () => {
    const res = {
      run: { id: 9, workflow_id: 5, workflow_version: 1, status: 'pending', trigger_type: 'manual', trigger_ref: null, context: null, started_at: null, finished_at: null, error: null, created_by: 1, created_at: 't' },
      nodes: [{ id: 1, run_id: 9, node_key: 'a', node_type: 'sleep', status: 'pending', exec_task_id: null, approval_id: null, attempt: 0, output: null, error: null, started_at: null, finished_at: null }],
    }
    vi.mocked(http.get).mockResolvedValue(ok(res))
    const result = await getWorkflowRun(9)
    expect(http.get).toHaveBeenCalledWith('/workflow-runs/9')
    expect(result.run.id).toBe(9)
    expect(result.nodes[0].node_key).toBe('a')
  })

  it('fetches the run ws-token (P3-4b engine tuple §A)', async () => {
    vi.mocked(http.get).mockResolvedValue(ok({ token: 'jwt-xyz' }))
    const result = await getWorkflowRunWsToken(9)
    expect(http.get).toHaveBeenCalledWith('/workflow-runs/9/ws-token')
    expect(result).toBe('jwt-xyz')
  })

  it('cancels a run -> run out', async () => {
    const row = { id: 9, workflow_id: 5, workflow_version: 1, status: 'cancelled', trigger_type: 'manual', trigger_ref: null, context: null, started_at: null, finished_at: 't', error: null, created_by: 1, created_at: 't' }
    vi.mocked(http.post).mockResolvedValue(ok(row))
    const result = await cancelWorkflowRun(9)
    expect(http.post).toHaveBeenCalledWith('/workflow-runs/9/cancel')
    expect(result.status).toBe('cancelled')
  })

  it('retries a run -> {run_id}', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ run_id: 12 }))
    const result = await retryWorkflowRun(9)
    expect(http.post).toHaveBeenCalledWith('/workflow-runs/9/retry')
    expect(result.run_id).toBe(12)
  })
})
