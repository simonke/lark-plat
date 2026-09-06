import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  getScripts,
  getScript,
  createScript,
  updateScript,
  deleteScript,
  getVersions,
  getVersion,
  rollbackScript,
  testScript
} from '../src/api/scripts'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn()
  }
}))

describe('Scripts API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should get scripts list with query params', async () => {
    const mockPage = { list: [{ id: 1, name: 's1' }], total: 1, page: 1, size: 10 }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockPage } })

    const result = await getScripts({ name: 's1', type: 'shell', page: 1, size: 10 })

    expect(http.get).toHaveBeenCalledWith('/scripts', {
      params: { name: 's1', type: 'shell', page: 1, size: 10 }
    })
    expect(result).toEqual(mockPage)
  })

  it('should omit params object when query is absent', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { list: [], total: 0 } } })

    await getScripts()

    expect(http.get).toHaveBeenCalledWith('/scripts', { params: undefined })
  })

  it('should get script detail without version param by default', async () => {
    const mockDetail = { id: 7, name: 's7', content: 'echo hi' }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockDetail } })

    const result = await getScript(7)

    expect(http.get).toHaveBeenCalledWith('/scripts/7', { params: undefined })
    expect(result).toEqual(mockDetail)
  })

  it('should pass specific version param when provided', async () => {
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: { id: 7 } } })

    await getScript(7, 3)

    expect(http.get).toHaveBeenCalledWith('/scripts/7', { params: { version: 3 } })
  })

  it('should create script', async () => {
    const payload = { name: 'new', type: 'shell', content: 'ls', params_def: null }
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: { id: 9 } } })

    const result = await createScript(payload)

    expect(http.post).toHaveBeenCalledWith('/scripts', payload)
    expect(result).toEqual({ id: 9 })
  })

  it('should update script (save as new version)', async () => {
    vi.mocked(http.put).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

    await updateScript(9, { content: 'pwd', change_log: 'fix' })

    expect(http.put).toHaveBeenCalledWith('/scripts/9', { content: 'pwd', change_log: 'fix' })
  })

  it('should delete script', async () => {
    vi.mocked(http.delete).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

    await deleteScript(9)

    expect(http.delete).toHaveBeenCalledWith('/scripts/9')
  })

  it('should list versions of a script', async () => {
    const versions = [{ id: 1, version: 1, content: 'a', change_log: 'init' }]
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: versions } })

    const result = await getVersions(9)

    expect(http.get).toHaveBeenCalledWith('/scripts/9/versions')
    expect(result).toEqual(versions)
  })

  it('should fetch a single version', async () => {
    const v = { id: 2, version: 2, content: 'b', change_log: 'update' }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: v } })

    const result = await getVersion(9, 2)

    expect(http.get).toHaveBeenCalledWith('/scripts/9/versions/2')
    expect(result).toEqual(v)
  })

  it('should rollback to given version', async () => {
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

    await rollbackScript(9, { version: 1 })

    expect(http.post).toHaveBeenCalledWith('/scripts/9/rollback', { version: 1 })
  })

  it('should test-run script and return {ok, errors[]}', async () => {
    const resultBody = { ok: false, errors: ['missing param target'] }
    vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: resultBody } })

    const result = await testScript(9, { params: { other: 1 } })

    expect(http.post).toHaveBeenCalledWith('/scripts/9/test', { params: { other: 1 } })
    expect(result).toEqual(resultBody)
  })
})
