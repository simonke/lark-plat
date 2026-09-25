import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getRelations,
  createRelation,
  deleteRelation,
  getTopology,
  getImpact,
} from '../src/api/assets'
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

describe('CMDB relation/topology API (P3-3)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('lists relations with query params', async () => {
    const page = { list: [{ id: 1, rel_type: 'depends_on' }], total: 1, page: 1, size: 20 }
    vi.mocked(http.get).mockResolvedValue(ok(page))
    const result = await getRelations({ rel_type: 'depends_on', src_id: 3, page: 1, size: 20 })
    expect(http.get).toHaveBeenCalledWith('/assets/relations', {
      params: { rel_type: 'depends_on', src_id: 3, page: 1, size: 20 },
    })
    expect(result).toEqual(page)
  })

  it('creates a relation (idempotent contract)', async () => {
    const row = {
      id: 7,
      src_type: 'host',
      src_id: 1,
      dst_type: 'host',
      dst_id: 2,
      rel_type: 'depends_on',
      properties: null,
      remark: '',
      created_by: 1,
      created_at: '2026-09-24T00:00:00',
      updated_at: '2026-09-24T00:00:00',
    }
    vi.mocked(http.post).mockResolvedValue(ok(row))
    const result = await createRelation({
      src_type: 'host',
      src_id: 1,
      dst_type: 'host',
      dst_id: 2,
      rel_type: 'depends_on',
    })
    expect(http.post).toHaveBeenCalledWith('/assets/relations', {
      src_type: 'host',
      src_id: 1,
      dst_type: 'host',
      dst_id: 2,
      rel_type: 'depends_on',
    })
    expect(result).toEqual(row)
  })

  it('deletes a relation by id', async () => {
    vi.mocked(http.delete).mockResolvedValue(ok(null))
    await deleteRelation(9)
    expect(http.delete).toHaveBeenCalledWith('/assets/relations/9')
  })

  it('fetches topology with direction/depth params', async () => {
    const topo = {
      nodes: [{ type: 'host', id: 1, label: 'h1', role: 'root' }],
      edges: [],
      truncated: false,
    }
    vi.mocked(http.get).mockResolvedValue(ok(topo))
    const result = await getTopology({ entity_type: 'host', entity_id: 1, direction: 'down', depth: 2 })
    expect(http.get).toHaveBeenCalledWith('/assets/cmdb/topology', {
      params: { entity_type: 'host', entity_id: 1, direction: 'down', depth: 2 },
    })
    expect(result).toEqual(topo)
  })

  it('fetches impact analysis (root carries label, affected is role-less)', async () => {
    const impact = {
      root: { type: 'host', id: 1, label: 'h1' },
      affected: [{ type: 'host', id: 2, label: 'h2' }],
      count: 1,
      truncated: false,
    }
    vi.mocked(http.get).mockResolvedValue(ok(impact))
    const result = await getImpact({ entity_type: 'host', entity_id: 1, direction: 'down', depth: 2 })
    expect(http.get).toHaveBeenCalledWith('/assets/cmdb/impact', {
      params: { entity_type: 'host', entity_id: 1, direction: 'down', depth: 2 },
    })
    expect(result.count).toBe(1)
    expect(result.root.label).toBe('h1')
  })
})
