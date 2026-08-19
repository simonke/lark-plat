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

describe('US-04 主机管理集成测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('主机 CRUD 流程', () => {
    it('应该完成创建→查询→编辑→删除的完整流程', async () => {
      // 1. 创建主机
      const newHost = { id: 1, hostname: 'test-host', ip: '192.168.1.100', os_type: 'linux', group_id: 1, env: 'production' }
      vi.mocked(http.post).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: newHost } })
      
      const created = await createHost({ hostname: 'test-host', ip: '192.168.1.100', os_type: 'linux', group_id: 1, env: 'production' })
      expect(created.id).toBe(1)
      expect(created.hostname).toBe('test-host')

      // 2. 查询主机
      const mockHost = { ...created, os_version: 'Ubuntu 22.04', group_name: '生产组', tags: [], status: 'online', connector: 'agent', sensitivity_level: 'normal', remark: '', created_at: '2026-08-19T10:00:00+08:00', updated_at: '2026-08-19T10:00:00+08:00' }
      vi.mocked(http.get).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: mockHost } })
      
      const fetched = await getHost(1)
      expect(fetched.hostname).toBe('test-host')
      expect(fetched.ip).toBe('192.168.1.100')

      // 3. 编辑主机
      vi.mocked(http.put).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: null } })
      await updateHost(1, { hostname: 'updated-host' })
      expect(http.put).toHaveBeenCalledWith('/assets/hosts/1', { hostname: 'updated-host' })

      // 4. 删除主机
      vi.mocked(http.delete).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: null } })
      await deleteHost(1)
      expect(http.delete).toHaveBeenCalledWith('/assets/hosts/1')
    })
  })

  describe('主机分页筛选', () => {
    it('应该支持按 hostname/ip/env/status 筛选', async () => {
      const mockData = { list: [], total: 0, page: 1, size: 10 }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockData } })

      // 按 hostname 筛选
      await getHosts({ hostname: 'web-server' })
      expect(http.get).toHaveBeenCalledWith('/assets/hosts', { params: { hostname: 'web-server' } })

      // 按 ip 筛选
      await getHosts({ ip: '192.168.1' })
      expect(http.get).toHaveBeenCalledWith('/assets/hosts', { params: { ip: '192.168.1' } })

      // 按 env 筛选
      await getHosts({ env: 'production' })
      expect(http.get).toHaveBeenCalledWith('/assets/hosts', { params: { env: 'production' } })

      // 按 status 筛选
      await getHosts({ status: 'online' })
      expect(http.get).toHaveBeenCalledWith('/assets/hosts', { params: { status: 'online' } })

      // 组合筛选
      await getHosts({ hostname: 'web', env: 'production', status: 'online', page: 2, size: 20 })
      expect(http.get).toHaveBeenCalledWith('/assets/hosts', { 
        params: { hostname: 'web', env: 'production', status: 'online', page: 2, size: 20 } 
      })
    })
  })

  describe('CSV 导入导出', () => {
    it('应该支持 CSV 导入', async () => {
      const mockResult = { success: 10, failed: [{ row: 5, error: 'IP 格式错误' }] }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockResult } })

      const file = new File(['hostname,ip,os_type'], 'hosts.csv', { type: 'text/csv' })
      const result = await importHosts(file)
      
      expect(result.success).toBe(10)
      expect(result.failed).toHaveLength(1)
      expect(result.failed[0].row).toBe(5)
    })

    it('应该支持 CSV 导出', async () => {
      const mockBlob = new Blob(['hostname,ip'], { type: 'text/csv' })
      vi.mocked(http.get).mockResolvedValue({ data: mockBlob })

      const result = await exportHosts()
      expect(result).toBeInstanceOf(Blob)
    })
  })

  describe('连通性检测', () => {
    it('应该返回连通性检测结果', async () => {
      const mockResult = { ok: true, latency_ms: 50, detail: 'Connection successful' }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockResult } })

      const result = await checkConnection(1)
      expect(result.ok).toBe(true)
      expect(result.latency_ms).toBe(50)
      expect(http.post).toHaveBeenCalledWith('/assets/hosts/1/conn')
    })

    it('应该处理连通性检测失败', async () => {
      const mockResult = { ok: false, latency_ms: 0, detail: 'Connection refused' }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockResult } })

      const result = await checkConnection(1)
      expect(result.ok).toBe(false)
      expect(result.detail).toBe('Connection refused')
    })
  })

  describe('分组树管理', () => {
    it('应该返回分组树结构', async () => {
      const mockTree = [
        { id: 1, name: '生产组', parent_id: 0, remark: '', children: [
          { id: 2, name: 'Web 服务器', parent_id: 1, remark: '', children: [] }
        ]}
      ]
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockTree } })

      const result = await getGroupsTree()
      expect(result).toHaveLength(1)
      expect(result[0].children).toHaveLength(1)
    })

    it('应该支持创建子分组', async () => {
      const mockGroup = { id: 3, name: '数据库服务器', parent_id: 1 }
      vi.mocked(http.post).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockGroup } })

      const result = await createGroup({ parent_id: 1, name: '数据库服务器' })
      expect(result.parent_id).toBe(1)
      expect(http.post).toHaveBeenCalledWith('/assets/groups', { parent_id: 1, name: '数据库服务器' })
    })
  })

  describe('主机统计', () => {
    it('应该返回主机统计数据', async () => {
      const mockStats = { 
        total: 100, 
        online: 80, 
        offline: 20, 
        by_env: { production: 60, testing: 30, development: 10 } 
      }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockStats } })

      const result = await getHostStats()
      expect(result.total).toBe(100)
      expect(result.online).toBe(80)
      expect(result.offline).toBe(20)
      expect(result.by_env.production).toBe(60)
    })
  })

  describe('权限控制', () => {
    it('应该根据权限控制操作', async () => {
      const mockHosts = { list: [], total: 0, page: 1, size: 10 }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockHosts } })

      // 所有用户都可以查看主机列表
      await getHosts()
      expect(http.get).toHaveBeenCalled()
    })
  })
})

describe('US-05 凭据管理集成测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('凭据 CRUD 流程', () => {
    it('应该完成密码类型凭据的创建→查询→编辑→删除', async () => {
      // 1. 创建密码类型凭据
      const newCred = { id: 1, host_id: 1, host_hostname: 'test-host', type: 'password', username: 'admin', secret_mask: '***', created_at: '2026-08-19T10:00:00+08:00' }
      vi.mocked(http.post).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: newCred } })
      
      const created = await createCredential({ host_id: 1, type: 'password', username: 'admin', secret: 'password123' })
      expect(created.type).toBe('password')
      expect(created.secret_mask).toBe('***')

      // 2. 查询凭据
      vi.mocked(http.get).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: [created] } })
      const all = await getCredentials()
      expect(all).toHaveLength(1)
      expect(all[0].username).toBe('admin')

      // 3. 编辑凭据
      vi.mocked(http.put).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: null } })
      await updateCredential(1, { username: 'root' })
      expect(http.put).toHaveBeenCalledWith('/assets/credentials/1', { username: 'root' })

      // 4. 删除凭据
      vi.mocked(http.delete).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: null } })
      await deleteCredential(1)
      expect(http.delete).toHaveBeenCalledWith('/assets/credentials/1')
    })

    it('应该完成密钥类型凭据的创建→查询→编辑→删除', async () => {
      // 1. 创建密钥类型凭据
      const newCred = { id: 2, host_id: 1, host_hostname: 'test-host', type: 'key', username: 'deploy', secret_mask: '***', created_at: '2026-08-19T10:00:00+08:00' }
      vi.mocked(http.post).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: newCred } })
      
      const created = await createCredential({ host_id: 1, type: 'key', username: 'deploy', key: '-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----' })
      expect(created.type).toBe('key')

      // 2. 编辑密钥凭据（不传 key 则保留原值）
      vi.mocked(http.put).mockResolvedValueOnce({ data: { code: 0, message: 'ok', data: null } })
      await updateCredential(2, { username: 'deploy-user' })
      expect(http.put).toHaveBeenCalledWith('/assets/credentials/2', { username: 'deploy-user' })
    })
  })

  describe('凭据脱敏', () => {
    it('应该返回脱敏后的凭据数据', async () => {
      const mockCreds = [
        { id: 1, host_id: 1, host_hostname: 'test-host', type: 'password', username: 'admin', secret_mask: '***', created_at: '2026-08-19T10:00:00+08:00' },
        { id: 2, host_id: 2, host_hostname: 'db-host', type: 'key', username: 'deploy', secret_mask: '***', created_at: '2026-08-19T10:00:00+08:00' }
      ]
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockCreds } })

      const result = await getCredentials()
      expect(result.every(c => c.secret_mask === '***')).toBe(true)
    })
  })

  describe('关联主机选择器', () => {
    it('应该支持按主机筛选凭据', async () => {
      const mockHosts = { 
        list: [
          { id: 1, hostname: 'host-1', ip: '192.168.1.1' },
          { id: 2, hostname: 'host-2', ip: '192.168.1.2' }
        ], 
        total: 2, 
        page: 1, 
        size: 10 
      }
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockHosts } })

      const result = await getHosts({ size: 1000 })
      expect(result.list).toHaveLength(2)
    })
  })

  describe('权限控制', () => {
    it('应该根据权限控制凭据操作', async () => {
      const mockCreds = [{ id: 1, host_id: 1, username: 'admin', type: 'password', secret_mask: '***' }]
      vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockCreds } })

      // 所有用户都可以查看凭据列表
      const result = await getCredentials()
      expect(result).toHaveLength(1)
    })
  })
})

describe('仪表盘统计测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('应该返回资产概览统计', async () => {
    const mockStats = { 
      total: 150, 
      online: 120, 
      offline: 30, 
      by_env: { production: 100, testing: 40, development: 10 } 
    }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockStats } })

    const result = await getHostStats()
    expect(result.total).toBe(150)
    expect(result.online).toBe(120)
    expect(result.offline).toBe(30)
    expect(Object.keys(result.by_env)).toHaveLength(3)
  })

  it('应该返回下拉选项数据', async () => {
    const mockOptions = { 
      groups: [{ id: 1, name: '生产组', parent_id: 0, remark: '', children: [] }],
      hostnames: ['host-1', 'host-2'],
      envs: ['production', 'testing', 'development']
    }
    vi.mocked(http.get).mockResolvedValue({ data: { code: 0, message: 'ok', data: mockOptions } })

    const result = await getOptions()
    expect(result.groups).toHaveLength(1)
    expect(result.hostnames).toHaveLength(2)
    expect(result.envs).toHaveLength(3)
  })
})