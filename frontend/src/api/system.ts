import { http, request } from './http'
import type {
  AuditLogOut,
  AuditLogQuery,
  GroupIdsIn,
  GroupOut,
  Page,
  PermissionNode,
  ResetPasswordIn,
  RoleCreate,
  RoleIdsIn,
  RoleOut,
  RoleUpdate,
  UserCreate,
  UserOut,
  UserRolesIn,
  UserStatusIn,
  UserUpdate,
} from './types'

export interface UserListQuery {
  username?: string
  real_name?: string
  status?: number
  role_id?: number
  page?: number
  size?: number
}

export const listUsers = (params: UserListQuery): Promise<Page<UserOut>> =>
  request({ url: '/system/users', method: 'get', params })

export const createUser = (data: UserCreate): Promise<{ id: number }> =>
  request({ url: '/system/users', method: 'post', data })

export const updateUser = (userId: number, data: UserUpdate): Promise<null> =>
  request({ url: `/system/users/${userId}`, method: 'put', data })

export const deleteUser = (userId: number): Promise<null> =>
  request({ url: `/system/users/${userId}`, method: 'delete' })

export const setUserRoles = (userId: number, data: UserRolesIn): Promise<null> =>
  request({ url: `/system/users/${userId}/roles`, method: 'put', data })

export const setUserStatus = (userId: number, data: UserStatusIn): Promise<null> =>
  request({ url: `/system/users/${userId}/status`, method: 'put', data })

export const resetPassword = (userId: number, data: ResetPasswordIn): Promise<null> =>
  request({ url: `/system/users/${userId}/password`, method: 'put', data })

export const listRoles = (): Promise<RoleOut[]> => request({ url: '/system/roles', method: 'get' })

export const createRole = (data: RoleCreate): Promise<{ id: number }> =>
  request({ url: '/system/roles', method: 'post', data })

export const updateRole = (roleId: number, data: RoleUpdate): Promise<null> =>
  request({ url: `/system/roles/${roleId}`, method: 'put', data })

export const deleteRole = (roleId: number): Promise<null> =>
  request({ url: `/system/roles/${roleId}`, method: 'delete' })

export const setRolePermissions = (roleId: number, data: RoleIdsIn): Promise<null> =>
  request({ url: `/system/roles/${roleId}/permissions`, method: 'put', data })

export const setRoleGroups = (roleId: number, data: GroupIdsIn): Promise<null> =>
  request({ url: `/system/roles/${roleId}/groups`, method: 'put', data })

export const listPermissions = (): Promise<PermissionNode[]> =>
  request({ url: '/system/permissions', method: 'get' })

export const listGroupTree = (): Promise<GroupOut[]> => request({ url: '/assets/groups/tree', method: 'get' })

export const listAuditLogs = (params: AuditLogQuery): Promise<Page<AuditLogOut>> =>
  request({ url: '/system/audit-logs', method: 'get', params })

export const getAuditLog = (logId: number): Promise<AuditLogOut> =>
  request({ url: `/system/audit-logs/${logId}`, method: 'get' })

export const exportAuditLogs = (params: Omit<AuditLogQuery, 'page' | 'size'>): Promise<void> =>
  http
    .get('/system/audit-logs/export', { params, responseType: 'blob' })
    .then((resp) => {
      const blob = resp.data as Blob
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'audit-logs.csv'
      a.click()
      window.URL.revokeObjectURL(url)
    })
