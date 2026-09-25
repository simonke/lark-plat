import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  listCicdProviders,
  createCicdProvider,
  updateCicdProvider,
  deleteCicdProvider,
  testCicdProvider,
} from '../src/api/cicd'
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

const PROVIDER = {
  id: 3,
  type: 'gitlab' as const,
  name: 'gl',
  endpoint: 'https://gitlab.example.com',
  enabled: 1,
  status: 'online',
  last_heartbeat: 't',
  created_by: 1,
  created_at: 't',
  updated_at: 't',
}

describe('cicd provider API (P3-5)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists providers with query params (Page envelope)', async () => {
    const page = { list: [PROVIDER], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await listCicdProviders({ name: 'gl', type: 'gitlab', page: 1, size: 10 })
    expect(http.get).toHaveBeenCalledWith('/cicd/providers', {
      params: { name: 'gl', type: 'gitlab', page: 1, size: 10 },
    })
    expect(result.list[0].type).toBe('gitlab')
  })

  it('creates a provider (POST /cicd/providers)', async () => {
    vi.mocked(http.post).mockResolvedValue(ok(PROVIDER))
    const result = await createCicdProvider({
      type: 'gitlab',
      name: 'gl',
      endpoint: 'https://gitlab.example.com',
      config: { token: 's' },
    })
    expect(http.post).toHaveBeenCalledWith('/cicd/providers', {
      type: 'gitlab',
      name: 'gl',
      endpoint: 'https://gitlab.example.com',
      config: { token: 's' },
    })
    expect(result.id).toBe(3)
  })

  it('updates a provider (PUT /cicd/providers/{id})', async () => {
    vi.mocked(http.put).mockResolvedValue(ok({ ...PROVIDER, name: 'gl2', enabled: 0 }))
    const result = await updateCicdProvider(3, { name: 'gl2', enabled: 0 })
    expect(http.put).toHaveBeenCalledWith('/cicd/providers/3', { name: 'gl2', enabled: 0 })
    expect(result.enabled).toBe(0)
  })

  it('deletes a provider', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok(null))
    await deleteCicdProvider(3)
    expect(http.delete).toHaveBeenCalledWith('/cicd/providers/3')
  })

  it('tests a provider (POST /cicd/providers/{id}/test) -> {ok,status}', async () => {
    vi.mocked(http.post).mockResolvedValue(ok({ id: 3, type: 'gitlab', name: 'gl', status: 'ok', ok: true }))
    const result = await testCicdProvider(3)
    expect(http.post).toHaveBeenCalledWith('/cicd/providers/3/test')
    expect(result.ok).toBe(true)
    expect(result.status).toBe('ok')
  })
})
