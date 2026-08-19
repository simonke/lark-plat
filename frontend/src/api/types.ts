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

export interface HostOut {
  id: number
  hostname: string
  ip: string
  os_type: string
  os_version: string
  group_id: number
  group_name: string
  env: string
  tags: string[]
  connector: string
  sensitivity_level: string
  status: string
  remark: string
  created_at: string
  updated_at: string
}

export interface HostCreate {
  hostname: string
  ip: string
  os_type: string
  os_version?: string
  group_id: number
  env: string
  tags?: string[]
  connector?: string
  sensitivity_level?: string
  remark?: string
}

export interface HostUpdate {
  hostname?: string | null
  ip?: string | null
  os_type?: string | null
  os_version?: string | null
  group_id?: number | null
  env?: string | null
  tags?: string[] | null
  connector?: string | null
  sensitivity_level?: string | null
  remark?: string | null
}

export interface CredentialOut {
  id: number
  host_id: number
  host_hostname: string
  type: string
  username: string
  secret_mask: string
  created_at: string
}

export interface CredentialCreate {
  host_id: number
  type: 'password' | 'key'
  username: string
  secret?: string
  key?: string
  passphrase?: string
}

export interface CredentialUpdate {
  username?: string | null
  secret?: string | null
  key?: string | null
  passphrase?: string | null
}

export interface HostStats {
  total: number
  online: number
  offline: number
  by_env: Record<string, number>
}

export interface ConnectionResult {
  ok: boolean
  latency_ms: number
  detail: string
}

export interface OptionsOut {
  groups: GroupOut[]
  hostnames: string[]
  envs: string[]
}
