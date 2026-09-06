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

export interface GroupCreate {
  parent_id?: number | null
  name: string
  sort?: number
  remark?: string
}

export interface GroupUpdate {
  name?: string | null
  parent_id?: number | null
  sort?: number | null
  remark?: string | null
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
/**
 * Stage 3 type additions — append to frontend/src/api/types.ts
 * Shapes mirror backend/app/schemas/__init__.py at e04d85e (script/exec/approval families).
 */

// ---------------------------------------------------------------- script

export interface ScriptCreate {
  name: string
  type?: string
  content: string
  params_def?: Record<string, unknown> | null
  remark?: string
}

export interface ScriptUpdate {
  content?: string | null
  params_def?: Record<string, unknown> | null
  change_log?: string
  remark?: string | null
}

export interface ScriptOut {
  id: number
  name: string
  type: string
  current_version: number
  params_def: Record<string, unknown> | null
  remark: string
  created_by: number | null
  created_at: string
}

export interface ScriptDetail extends ScriptOut {
  content: string
}

export interface ScriptVersionOut {
  id: number
  script_id: number
  version: number
  content: string
  params_def: Record<string, unknown> | null
  change_log: string
  created_by: number | null
  created_at: string
}

export interface RollbackIn {
  version: number
}

export interface ScriptTestIn {
  params?: Record<string, unknown> | null
}

export interface ScriptTestResult {
  ok: boolean
  errors: string[]
}

export interface ScriptQuery {
  name?: string
  type?: string
  page?: number
  size?: number
}

// ---------------------------------------------------------------- exec

export interface ExecTaskCreate {
  name: string
  kind?: 'command' | 'script'
  script_id?: number | null
  script_version?: number | null
  command?: string | null
  params?: Record<string, unknown> | null
  target_host_ids: number[]
  mode?: string
  timeout_sec?: number
  retry?: number
}

export interface ExecTaskOut {
  id: number
  task_no: string
  name: string
  kind: string
  script_id: number | null
  script_version: number | null
  command: string | null
  params: Record<string, unknown> | null
  target_host_ids: Record<string, unknown> | null
  mode: string
  timeout_sec: number
  retry: number
  sensitive_flag: number
  approve_required: number
  approval_id: number | null
  status: string
  created_by: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ExecHostOut {
  id: number
  host_id: number
  hostname: string
  ip: string
  executor: string
  status: string
  exit_code: number | null
  started_at: string | null
  finished_at: string | null
}

export interface ExecTaskDetail extends ExecTaskOut {
  hosts: ExecHostOut[]
  approval_status: string | null
}

export interface ExecLogOut {
  seq: number
  level: string
  content: string
  created_at: string
}

export interface ExecLogPage {
  list: ExecLogOut[]
  next_seq: number
}

export interface ExecStats {
  total: number
  pending: number
  running: number
  success: number
  failed: number
  timed_out: number
  canceled: number
}

export interface ExecTaskQuery {
  task_no?: string
  name?: string
  status?: string
  kind?: string
  start?: string
  end?: string
  page?: number
  size?: number
}

export interface WsTokenOut {
  token: string
}

// ---------------------------------------------------------------- approval (stage 4 preview, types only)

export interface ApproveIn {
  comment?: string
}

export interface ApprovalOut {
  id: number
  request_no: string
  biz_type: string
  biz_id: number
  title: string
  reason: string
  requester_id: number
  sensitive_hit: string
  status: string
  approver_id: number | null
  decided_at: string | null
  created_at: string
  version: number
}

export interface ApprovalRecordOut {
  action: string
  operator_id: number
  comment: string
  created_at: string
}

export interface ApprovalDetail extends ApprovalOut {
  timeline: ApprovalRecordOut[]
}

export interface ApprovalQuery {
  status?: string
  biz_type?: string
  mine?: boolean
  todo?: boolean
  page?: number
  size?: number
}

export interface RuleIn {
  name: string
  kind: string
  value: Record<string, unknown>
  enabled?: number
}

export interface RuleOut {
  id: number
  name: string
  kind: string
  value: Record<string, unknown>
  enabled: number
  created_at: string
}

// ---------------------------------------------------------------- notify (stage 4)

export interface ChannelCreate {
  name: string
  type: string
  config: Record<string, unknown>
  enabled?: number
}

export interface ChannelUpdate {
  name?: string | null
  config?: Record<string, unknown> | null
  enabled?: number | null
}

export interface ChannelOut {
  id: number
  name: string
  type: string
  enabled: number
  config_mask: Record<string, unknown>
  created_at: string
}

export interface ChannelStatusIn {
  enabled: number
}

export interface ChannelTestIn {
  title?: string
  content?: string
}

export interface NotifyRecordOut {
  id: number
  channel_id: number | null
  scene: string
  target: string
  title: string
  content: string
  status: string
  error_msg: string | null
  sent_at: string | null
  created_at: string
}

export interface NotifyRecordQuery {
  channel_id?: number
  scene?: string
  status?: string
  start?: string
  end?: string
  page?: number
  size?: number
}

// ---------------------------------------------------------------- terminal (stage 4)

export interface TerminalCreate {
  host_id: number
  cols?: number
  rows?: number
  reason?: string
}

export interface TerminalOut {
  id: number
  session_no: string
  host_id: number
  user_id: number
  status: string
  close_reason: string
  sensitive: number
  approval_id: number | null
  version: number
  started_at: string | null
  finished_at: string | null
  duration_sec: number
  bytes_out: number
  bytes_in: number
}

export interface TerminalCreateOut {
  id: number
  session_no: string
  host_id: number
  status: string
  sensitive: number
  approval_id: number | null
  ws_token: string | null
}

export interface TerminalTokenOut {
  session_id: number
  session_no: string
  ws_token: string
  expires_in: number
}

export interface TerminalRequestOut extends TerminalCreateOut {
  require_approval: boolean
}

export interface TerminalRecordingChunkOut {
  offset: number
  data: string
  created_at: string | null
}

export interface TerminalRecordingOut {
  session_id: number
  after_offset: number
  size: number
  has_more: boolean
  chunks: TerminalRecordingChunkOut[]
}

export interface TerminalQuery {
  status?: string
  page?: number
  size?: number
}


