import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listReleases,
  createRelease,
  getRelease,
  canaryRelease,
  promoteRelease,
  rollbackRelease,
  cancelRelease,
} from '../src/api/release'
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

const RELEASE = {
  id: 7,
  provider_id: 3,
  app: 'svc-a',
  env: 'dev' as const,
  version: '1.0.0',
  status: 'pending' as const,
  workflow_run_id: null,
  target_host_ids: null,
  rolled_back_from: null,
  created_by: 1,
  created_at: 't',
  updated_at: 't',
}

describe('release API (P3-5)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists releases with query params (Page envelope)', async () => {
    const page = { list: [RELEASE], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listReleases({ app: 'svc-a', env: 'dev', status: 'pending', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/releases', {
      params: { app: 'svc-a', env: 'dev', status: 'pending', page: 1, size: 10 },
    })
    expect(result.list[0].status).toBe('pending')
  })

  it('creates a release (POST /releases) -> status pending', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(RELEASE))
    const result = await createRelease({ provider_id: 3, app: 'svc-a', version: '1.0.0', env: 'dev' })
    expect(http.post).toHaveBeenCalledWith('/releases', {
      provider_id: 3,
      app: 'svc-a',
      version: '1.0.0',
      env: 'dev',
    })
    expect(result.status).toBe('pending')
  })

  it('gets a release detail (GET /releases/{id})', async () => {
    vi.mocked(http.get).mockResolvedValue(ok(RELEASE))
    const result = await getRelease(7)
    expect(http.get).toHaveBeenCalledWith('/releases/7')
    expect(result.id).toBe(7)
  })

  it('triggers canary (POST /releases/{id}/canary)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ ...RELEASE, status: 'canary' }))
    const result = await canaryRelease(7)
    expect(http.post).toHaveBeenCalledWith('/releases/7/canary')
    expect(result.status).toBe('canary')
  })

  it('promotes (POST /releases/{id}/promote)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ ...RELEASE, status: 'succeeded' }))
    const result = await promoteRelease(7)
    expect(http.post).toHaveBeenCalledWith('/releases/7/promote')
    expect(result.status).toBe('succeeded')
  })

  it('rolls back (POST /releases/{id}/rollback)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ ...RELEASE, status: 'rolled_back' }))
    const result = await rollbackRelease(7)
    expect(http.post).toHaveBeenCalledWith('/releases/7/rollback')
    expect(result.status).toBe('rolled_back')
  })

  it('cancels (POST /releases/{id}/cancel)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ ...RELEASE, status: 'cancelled' }))
    const result = await cancelRelease(7)
    expect(http.post).toHaveBeenCalledWith('/releases/7/cancel')
    expect(result.status).toBe('cancelled')
  })
})
