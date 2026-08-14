export interface Result<T = unknown> {
  code: number
  message: string
  data: T
}

export interface Page<T> {
  list: T[]
  total: number
  page: number
  size: number
}

export interface RoleBrief {
  id: number
  code: string
  name: string
}

export interface UserBrief {
  id: number
  username: string
  real_name: string
  roles: RoleBrief[]
}

export interface UserMe {
  id: number
  username: string
  real_name: string
  roles: RoleBrief[]
  permissions: string[]
  visible_group_ids: number[]
  is_admin: boolean
}

export interface TokenOut {
  access_token: string
  refresh_token: string
  token_type: string
  user: UserBrief
}

export interface LoginIn {
  username: string
  password: string
}

export interface RefreshIn {
  refresh_token: string
}

export interface ChangePasswordIn {
  old_password: string
  new_password: string
}

export interface UserOut {
  id: number
  username: string
  real_name: string
  phone: string
  email: string
  status: number
  last_login_at: string | null
  role_ids?: number[]
}

export interface UserCreate {
  username: string
  password: string
  real_name?: string
  phone?: string
  email?: string
  role_ids?: number[]
  status?: number
}

export interface UserUpdate {
  real_name?: string | null
  phone?: string | null
  email?: string | null
  status?: number | null
}

export interface UserRolesIn {
  role_ids: number[]
}

export interface UserStatusIn {
  status: number
}

export interface ResetPasswordIn {
  password: string
}

export interface RoleOut {
  id: number
  code: string
  name: string
  remark: string
  permission_ids?: number[]
  group_ids?: number[]
}

export interface RoleCreate {
  code: string
  name: string
  remark?: string
}

export interface RoleUpdate {
  name?: string | null
  remark?: string | null
}

export interface RoleIdsIn {
  permission_ids: number[]
}

export interface GroupIdsIn {
  group_ids: number[]
}

export interface PermissionNode {
  id: number
  parent_id: number
  code: string
  name: string
  type: string
  path: string
  icon: string
  sort: number
  children: PermissionNode[]
}

export interface GroupOut {
  id: number
  name: string
  parent_id: number
  remark: string
  children: GroupOut[]
}

export interface AuditLogOut {
  id: number
  user_id: number | null
  username: string
  module: string
  action: string
  method: string
  path: string
  params: Record<string, unknown> | null
  ip: string
  user_agent: string
  status: number
  cost_ms: number
  trace_id: string
  created_at: string
}

export interface AuditLogQuery {
  module?: string
  action?: string
  username?: string
  ip?: string
  start?: string
  end?: string
  page?: number
  size?: number
}
