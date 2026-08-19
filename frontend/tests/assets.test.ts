import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getHosts, getHost, createHost, updateHost, deleteHost, importHosts, exportHosts, checkConnection, getGroupsTree, createGroup, updateGroup, deleteGroup, getCredentials, createCredential, updateCredential, deleteCredential, getHostStats, getOptions } from '../src/api/assets'
import http from '../src/api/http'

vi.mock('../src/api/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn()
  }
}))

describe('Assets API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Hosts', () => {
    it('should get hosts list', async () => {
      const mockData = { list: [{ id: 1, hostname: 'test' }], total: 1, page: 1, size: 10 }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockData } })

      const result = await getHosts({ page: 1, size: 10 })

      expect(http.get).toHaveBeenCalledWith('/assets/hosts', { params: { page: 1, size: 10 } })
      expect(result).toEqual(mockData)
    })

    it('should get host detail', async () => {
      const mockHost = { id: 1, hostname: 'test-host' }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockHost } })

      const result = await getHost(1)

      expect(http.get).toHaveBeenCalledWith('/assets/hosts/1')
      expect(result).toEqual(mockHost)
    })

    it('should create host', async () => {
      const mockHost = { id: 1, hostname: 'new-host' }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockHost } })

      const result = await createHost({ hostname: 'new-host', ip: '1.2.3.4', os_type: 'linux', group_id: 1, env: 'production' })

      expect(http.post).toHaveBeenCalledWith('/assets/hosts', { hostname: 'new-host', ip: '1.2.3.4', os_type: 'linux', group_id: 1, env: 'production' })
      expect(result).toEqual(mockHost)
    })

    it('should update host', async () => {
      vi.mocked(http.put).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

      await updateHost(1, { hostname: 'updated-host' })

      expect(http.put).toHaveBeenCalledWith('/assets/hosts/1', { hostname: 'updated-host' })
    })

    it('should delete host', async () => {
      vi.mocked(http.delete).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

      await deleteHost(1)

      expect(http.delete).toHaveBeenCalledWith('/assets/hosts/1')
    })

    it('should check connection', async () => {
      const mockResult = { ok: true, latency_ms: 50, detail: 'success' }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockResult } })

      const result = await checkConnection(1)

      expect(http.post).toHaveBeenCalledWith('/assets/hosts/1/conn')
      expect(result).toEqual(mockResult)
    })

    it('should get host stats', async () => {
      const mockStats = { total: 100, online: 80, offline: 20, by_env: { production: 60, testing: 40 } }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockStats } })

      const result = await getHostStats()

      expect(http.get).toHaveBeenCalledWith('/assets/hosts/stats')
      expect(result).toEqual(mockStats)
    })
  })

  describe('Groups', () => {
    it('should get groups tree', async () => {
      const mockTree = [{ id: 1, name: 'group1', children: [] }]
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockTree } })

      const result = await getGroupsTree()

      expect(http.get).toHaveBeenCalledWith('/assets/groups/tree')
      expect(result).toEqual(mockTree)
    })

    it('should create group', async () => {
      const mockGroup = { id: 1, name: 'new-group' }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockGroup } })

      const result = await createGroup({ parent_id: 0, name: 'new-group' })

      expect(http.post).toHaveBeenCalledWith('/assets/groups', { parent_id: 0, name: 'new-group' })
      expect(result).toEqual(mockGroup)
    })

    it('should update group', async () => {
      vi.mocked(http.put).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

      await updateGroup(1, { name: 'updated-group' })

      expect(http.put).toHaveBeenCalledWith('/assets/groups/1', { name: 'updated-group' })
    })

    it('should delete group', async () => {
      vi.mocked(http.delete).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

      await deleteGroup(1)

      expect(http.delete).toHaveBeenCalledWith('/assets/groups/1')
    })
  })

  describe('Credentials', () => {
    it('should get credentials list', async () => {
      const mockCreds = [{ id: 1, host_id: 1, username: 'admin', type: 'password', secret_mask: '***' }]
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockCreds } })

      const result = await getCredentials()

      expect(http.get).toHaveBeenCalledWith('/assets/credentials')
      expect(result).toEqual(mockCreds)
    })

    it('should create credential', async () => {
      const mockCred = { id: 1, host_id: 1, username: 'admin', type: 'password', secret_mask: '***' }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockCred } })

      const result = await createCredential({ host_id: 1, type: 'password', username: 'admin', secret: 'password123' })

      expect(http.post).toHaveBeenCalledWith('/assets/credentials', { host_id: 1, type: 'password', username: 'admin', secret: 'password123' })
      expect(result).toEqual(mockCred)
    })

    it('should update credential', async () => {
      vi.mocked(http.put).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

      await updateCredential(1, { username: 'newuser' })

      expect(http.put).toHaveBeenCalledWith('/assets/credentials/1', { username: 'newuser' })
    })

    it('should delete credential', async () => {
      vi.mocked(http.delete).mockResolvedValue({ data: { code: 0, message: 'ok', data: null } })

      await deleteCredential(1)

      expect(http.delete).toHaveBeenCalledWith('/assets/credentials/1')
    })
  })

  describe('Options', () => {
    it('should get options', async () => {
      const mockOptions = { groups: [], hostnames: [], envs: [] }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockOptions } })

      const result = await getOptions()

      expect(http.get).toHaveBeenCalledWith('/assets/options')
      expect(result).toEqual(mockOptions)
    })
  })
})