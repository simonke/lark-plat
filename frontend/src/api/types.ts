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

export type AuthProviderType = 'ldap' | 'oauth2'

export interface AuthProviderBrief {
  code: string
  type: string
  name: string
}

export interface AuthProviderOut {
  id: number
  code: string
  name: string
  type: AuthProviderType
  enabled: number
  config_mask: Record<string, unknown>
  created_at: string
}

export interface AuthProviderCreate {
  name: string
  type: AuthProviderType
  code?: string
  config: Record<string, unknown>
  enabled?: number
}

export interface AuthProviderUpdate {
  name?: string
  config?: Record<string, unknown>
  enabled?: number
}

export interface AuthProviderStatusIn {
  enabled: number
}

export interface AuthProviderTestResult {
  ok: boolean
  latency_ms?: number
  error_message?: string | null
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

// ---------------------------------------------------------------- transfer (P2-1, api-design-v3 §1 frozen)
export type TransferMode = 'push' | 'pull'
export type TransferTaskStatus = 'processing' | 'success' | 'partial' | 'failed' | 'canceled'
export type TransferHostStatus =
  | 'pending'
  | 'pulling'
  | 'transferring'
  | 'verifying'
  | 'success'
  | 'failed'
  | 'verify_failed'
  | 'degraded'
  | 'canceled'

export interface TransferFileItem {
  path: string
  size: number
  sha256: string
}

export interface TransferUploadResult {
  package_id: number
  items: TransferFileItem[]
}

export interface TransferPackageOut {
  id: number
  name: string
  file_count: number
  total_size: number
  created_by: number | null
  created_at: string
}

export interface TransferPackageDetail extends TransferPackageOut {
  items: TransferFileItem[]
}

export interface TransferPackageQuery {
  name?: string
  start?: string
  end?: string
  page?: number
  size?: number
}

export interface TransferTaskCreate {
  mode: TransferMode
  package_id?: number
  source_host_id?: number
  source_host_path?: string
  target_path: string
  host_ids: number[]
  overwrite: 0 | 1
  verify: 0 | 1
  limit_mbps?: number
}

export interface TransferTaskCreated {
  id: number
  task_no: string
  status: TransferTaskStatus
  pending: number
}

export interface TransferTaskOut {
  id: number
  task_no: string
  mode: TransferMode
  package_id: number | null
  source_host_id: number | null
  source_host_path: string | null
  target_path: string
  host_ids: Record<string, unknown> | null
  overwrite: 0 | 1
  verify: 0 | 1
  limit_mbps: number | null
  status: TransferTaskStatus
  created_by: number | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface TransferHostOut {
  id: number
  host_id: number
  hostname: string
  ip: string
  channel: string
  status: TransferHostStatus
  current_offset: number
  verify_sha256: string | null
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export interface TransferLogHostOut {
  id: number
  hostname: string
}

export interface TransferTaskMineOut extends TransferTaskOut {
  hosts: TransferLogHostOut[]
}

export interface TransferTaskDetail extends TransferTaskOut {
  hosts: TransferHostOut[]
  stats: TransferStats
}

export interface TransferLogOut {
  seq: number
  level: string
  content: string
  created_at: string
}

export interface TransferLogPage {
  list: TransferLogOut[]
  next_seq: number
}

export interface TransferStats {
  total: number
  pending: number
  transferring: number
  verifying: number
  verify_failed: number
  success: number
  failed: number
}

export interface TransferTaskQuery {
  task_no?: string
  mode?: TransferMode
  status?: TransferTaskStatus
  start?: string
  end?: string
  page?: number
  size?: number
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

// ---------------------------------------------------------------- schedule (stage 7)

export interface ScheduleCreate {
  name: string
  kind: 'command' | 'script'
  script_id?: number | null
  command?: string | null
  params?: Record<string, unknown> | null
  trigger_type: 'cron' | 'interval'
  cron_expr?: string | null
  timezone?: string
  interval_sec?: number | null
  target_host_ids: number[]
  timeout_sec?: number
  retry?: number
  concurrency_limit?: number
  enabled?: number
}

export interface ScheduleUpdate {
  name?: string | null
  kind?: string | null
  script_id?: number | null
  command?: string | null
  params?: Record<string, unknown> | null
  trigger_type?: string | null
  cron_expr?: string | null
  timezone?: string | null
  interval_sec?: number | null
  target_host_ids?: number[] | null
  timeout_sec?: number | null
  retry?: number | null
  concurrency_limit?: number | null
}

export interface ScheduleOut {
  id: number
  name: string
  kind: string
  script_id: number | null
  command: string | null
  params: Record<string, unknown> | null
  trigger_type: string
  cron_expr: string | null
  timezone: string
  interval_sec: number | null
  target_host_ids: Record<string, unknown> | null
  timeout_sec: number
  retry: number
  concurrency_limit: number
  enabled: number
  created_by: number | null
  created_at: string
}

export interface ScheduleQuery {
  name?: string
  enabled?: number
  page?: number
  size?: number
}

export interface ScheduleRunOut {
  id: number
  schedule_task_id: number
  run_no: string
  status: string
  task_id: number | null
  started_at: string
  finished_at: string | null
  error_msg: string | null
}

export interface ScheduleRunNowResult {
  run_id: number
  task_id: number
  status: string
  approve_required: boolean
  approval_id: number | null
  sensitive_flag: boolean
}

export interface ScheduleRetryResult {
  run_id: number
  task_id: number
  status: string
  approve_required?: boolean
  approval_id?: number | null
  sensitive_flag?: boolean
}

// ---------------------------------------------------------------- dashboard (stage 7)

export interface DashboardStats {
  host_total: number
  host_online: number
  tasks_running: number
  today_tasks: number
  today_success: number
  pending_approvals: number
}

export interface TrendPoint {
  date: string
  total: number
  success: number
  failed: number
}

export interface RecentTask {
  id: number
  task_no: string
  name: string
  status: string
  kind: string
  created_at: string
}

export interface RecentApproval {
  id: number
  request_no: string
  title: string
  status: string
  created_at: string
}

// ---------------------------------------------------------------- monitoring (P2-MA v3.0)
// 归一化事件模型 MonEvent 契约 (api-design v3.0 §P2-MA)
export type MonEventKind = 'metric' | 'alert' | 'log' | 'apm'
export type MonSource = 'agent' | 'prometheus' | 'elk' | 'skywalking' | 'alertmanager' | 'webhook'
export type MonSeverity = 'critical' | 'warning' | 'info'

export interface MonEntity {
  entity_type: 'host' | 'app' | 'service'
  entity_id: string
  entity_name: string
}

export interface MonEvent {
  source: MonSource
  kind: MonEventKind
  entity: MonEntity
  ts: string
  value: number | null
  severity: MonSeverity | null
  labels: Record<string, unknown>
  raw: Record<string, unknown>
  fingerprint: string
}

// /monitor/metrics 查询参数（后端 acceptance: entity_ids/group_id/metric_name/start/end/agg/page/size）
export interface MonMetricQuery {
  entity_ids?: string
  group_id?: number
  metric_name?: string
  start?: string
  end?: string
  agg?: '5m' | '1h' | '1d'
  page?: number
  size?: number
}

// agg 命中时后端返回的分桶点
// 契约 §2 冻结 ts/value；bucket/avg/max/min/count/entity_id 为附加键（add-only，
// 架构师裁定 C：只加不改）。ts/value 暂标可选以兼容修复前后端旧形状。
export interface MonMetricBucket {
  ts?: string
  value?: number
  bucket?: string
  avg?: number
  max?: number
  min?: number
  count?: number
  entity_id?: string
}

// 未分桶时后端返回的原始采样点
export interface MonMetricSamplePoint {
  ts: string
  entity_id: string
  value: number
  source: MonSource
}

// GET /monitor/metrics 统一返回体：{agg, points, total?, page?, size?}
export interface MonMetricResult {
  agg: '5m' | '1h' | '1d' | null
  points: (MonMetricBucket | MonMetricSamplePoint)[]
  total?: number
  page?: number
  size?: number
}

// GET /monitor/metrics/current 返回 {list:[...]}
export interface MonCurrentMetric {
  entity_id: string
  metric_name: string
  value: number
  ts: string | null
}

// /monitor/alerts 查询参数（后端支持 status/severity/rule_id + 分页）
export interface MonAlertQuery {
  status?: string
  severity?: MonSeverity
  rule_id?: number
  entity_id?: string
  start?: string
  end?: string
  page?: number
  size?: number
}

// WS /ws/monitor 推送帧契约 (api-design-v3.md §2, S→C)
export type MonAlertAction = 'fire' | 'acknowledge' | 'escalate' | 'resolve' | 'suppress'

export interface MonAlertOut {
  id: number
  rule_id: number | null
  rule_name: string | null
  entity: MonEntity
  source: MonSource
  status: string
  severity: MonSeverity
  last_value: number | null
  fired_at: string | null
  resolved_at: string | null
  action: MonAlertAction
  ts: string | null
}

export interface MonMetricFrame {
  host_id: string
  metric_name: string
  value: number
  ts: string
}

export interface MonWsFrame<T = unknown> {
  type: 'hello' | 'alert' | 'metric' | 'pong' | string
  data: T
}

export interface MonSubscribeIn {
  scope?: string
  ids?: string[]
}

export interface MonHelloData {
  subscribed: boolean
  ids: string[]
}

export interface AlertRuleCreate {
  name: string
  description?: string
  enabled?: number
  event_source?: MonSource | null
  event_kind: MonEventKind
  metric_name?: string
  condition_operator: '>' | '<' | '>=' | '<=' | '==' | '!='
  condition_threshold: number
  condition_duration_seconds?: number
  scope_type?: string | null
  scope_ids?: string[] | null
  level?: string
  cooldown_seconds?: number
  converge_sec?: number
  escalation_enabled?: number
  escalation_after_seconds?: number
  escalation_severity?: MonSeverity
  escalate_levels?: string[] | null
  notify_scene?: string
  notify_channel_ids?: number[]
}

export interface AlertRuleUpdate {
  name?: string
  description?: string | null
  enabled?: number | null
  event_source?: MonSource | null
  event_kind?: MonEventKind
  metric_name?: string | null
  condition_operator?: string
  condition_threshold?: number
  condition_duration_seconds?: number
  scope_type?: string | null
  scope_ids?: string[] | null
  level?: string
  cooldown_seconds?: number
  converge_sec?: number
  escalation_enabled?: number | null
  escalation_after_seconds?: number
  escalation_severity?: MonSeverity
  escalate_levels?: string[] | null
  notify_scene?: string
  notify_channel_ids?: number[]
}

export interface AlertRuleOut {
  id: number
  name: string
  description: string | null
  enabled: number
  event_source: MonSource | null
  event_kind: MonEventKind
  metric_name: string | null
  condition_operator: string
  condition_threshold: number
  condition_duration_seconds: number
  scope_type: string | null
  scope_ids: string[] | null
  level: string
  cooldown_seconds: number
  converge_sec: number
  escalation_enabled: number
  escalation_after_seconds: number
  escalation_severity: MonSeverity
  escalate_levels: string[] | null
  notify_scene: string
  notify_channel_ids: number[]
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface AlertRuleQuery {
  enabled?: number
  event_kind?: MonEventKind
  page?: number
  size?: number
}

// GET /monitor/adapters 列表项（后端 _adapter_out）
export interface MonAdapterOut {
  id: number
  name: string
  type: MonSource
  endpoint: string | null
  config_mask: Record<string, unknown>
  enabled: number
  status: string
  last_heartbeat: string | null
  metrics_received_count: number
  error_msg: string | null
  created_by: number | null
  created_at: string | null
}

// POST /monitor/adapters/{id}/test 返回体（后端 test_adapter）
export interface AdapterTestResult {
  ok: boolean
  latency_ms: number | null
  error_message: string | null
}

// ---------------------------------------------------------------- ticket (P3-1, api-design-v3 §5)
// shapes @ backend/app/schemas/ticket.py (daab403)
export type TicketCategory = 'incident' | 'change' | 'request' | 'other'
export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent'
export type TicketStatus =
  | 'create'
  | 'assign'
  | 'accept'
  | 'processing'
  | 'done'
  | 'close'
  | 'cancel'
export type TicketRefType =
  | 'exec_task'
  | 'approval'
  | 'asset_host'
  | 'schedule'
  | 'kb_article'
  | 'script'

export interface TicketCreate {
  title: string
  category?: TicketCategory
  priority?: TicketPriority
  description?: string
  assignee_id?: number | null
  host_ids?: number[] | null
  due_at?: string | null
}

export interface TicketUpdate {
  title?: string
  category?: TicketCategory
  priority?: TicketPriority
  description?: string
  assignee_id?: number | null
  due_at?: string | null
}

export interface TicketOut {
  id: number
  ticket_no: string
  title: string
  category: string
  priority: string
  status: string
  requester_id: number | null
  assignee_id: number | null
  team_id: number | null
  description: string
  sla_due_at: string | null
  resolved_at: string | null
  closed_at: string | null
  version: number
  created_at: string
  updated_at?: string | null
}

export interface TicketRefOut {
  id: number
  ref_type: string
  ref_id: number
}

export interface TicketCommentOut {
  id: number
  author_id: number | null
  content: string
  created_at: string | null
}

export interface TicketAttachmentOut {
  id: number
  file_id: number
  filename: string
  size: number
  created_at: string | null
}

export interface TicketDetail extends TicketOut {
  refs: TicketRefOut[]
  comments: TicketCommentOut[]
  attachments: TicketAttachmentOut[]
}

export interface TicketQuery {
  ticket_no?: string
  category?: string
  status?: string
  priority?: string
  requester_id?: number
  assignee_id?: number
  start?: string
  end?: string
  page?: number
  size?: number
}

export interface TicketAssignIn {
  assignee_id: number
}

export interface TicketDoneIn {
  remark?: string
  exec_task_id?: number | null
}

export interface TicketRefIn {
  ref_type: string
  ref_id: number
}

// ---------------------------------------------------------------- kb (P3-2, api-design-v3 §6)
// shapes @ backend/app/schemas/kb.py (daab403)
export type KbVisibility = 'public' | 'internal' | 'classified'

export interface KbArticleCreate {
  title: string
  category_id?: number | null
  visibility?: KbVisibility
  content: string
  summary?: string
  tags?: string[] | null
}

export interface KbArticleUpdate {
  title?: string
  category_id?: number | null
  visibility?: KbVisibility
  content?: string
  summary?: string
  change_log?: string
}

export interface KbArticleOut {
  id: number
  title: string
  category_id: number | null
  visibility: string
  current_version: number
  author_id: number | null
  summary: string
  created_at: string | null
  updated_at: string | null
}

export interface KbArticleDetail extends KbArticleOut {
  content: string
  tags: string[]
}

export interface KbArticleVersionOut {
  id: number
  version: number
  title: string
  change_log: string
  editor_id: number | null
  created_at: string | null
}

export interface KbVersionListOut {
  article_id: number
  current_version: number
  list: KbArticleVersionOut[]
}

export interface KbVersionOut {
  article_id: number
  version: number
  title: string
  content: string
  change_log: string
  editor_id: number | null
  created_at: string | null
}

export interface KbCategoryNode {
  id: number
  parent_id: number
  name: string
  sort: number
  children: KbCategoryNode[]
}

export interface KbCategoryListOut {
  tree: KbCategoryNode[]
  total: number
}

export interface KbCategoryOut {
  id: number
  parent_id: number
  name: string
  sort: number
}

export interface KbCategoryCreate {
  name: string
  parent_id?: number | null
  sort?: number
}

export interface KbCategoryUpdate {
  name?: string
  parent_id?: number | null
  sort?: number
}

export interface KbArticleQuery {
  keyword?: string
  category_id?: number
  tag?: string
  visibility?: KbVisibility
  page?: number
  size?: number
}

export type RelationEntityType = 'host' | 'host_group'
export type CmdbRelType = 'depends_on' | 'runs_on' | 'connects_to' | 'member_of' | 'hosts'
export type TopoNodeRole = 'root' | 'up' | 'down'

export interface EntityRelation {
  id: number
  src_type: RelationEntityType
  src_id: number
  dst_type: RelationEntityType
  dst_id: number
  rel_type: CmdbRelType
  properties: Record<string, unknown> | null
  remark: string
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface EntityRelationCreate {
  src_type: RelationEntityType
  src_id: number
  dst_type: RelationEntityType
  dst_id: number
  rel_type: CmdbRelType
  properties?: Record<string, unknown> | null
  remark?: string
}

export interface TopoNode {
  type: RelationEntityType
  id: number
  label: string
  role: TopoNodeRole
}

export interface TopoEdge {
  src: { type: RelationEntityType; id: number }
  dst: { type: RelationEntityType; id: number }
  rel_type: CmdbRelType
}

export interface Topology {
  nodes: TopoNode[]
  edges: TopoEdge[]
  truncated: boolean
}

export interface ImpactEntity {
  type: RelationEntityType
  id: number
  label?: string
}

export interface CmdbImpact {
  root: ImpactEntity
  affected: ImpactEntity[]
  count: number
  truncated: boolean
}


