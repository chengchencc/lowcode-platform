/** 实例与任务的 TS 类型，与 backend/app/schemas/instance.py 对齐。 */

import type { FieldState } from '@/types/form'
import type { FormSchema } from '@/types/form'

export type InstanceStatus =
  | 'DRAFT'
  | 'RUNNING'
  | 'REJECTED'
  | 'APPROVED'
  | 'WITHDRAWN'
  | 'TERMINATED'

export type TaskAction = 'AGREE' | 'REJECT' | 'RETURN' | 'SUBMIT'

export interface InstanceItem {
  id: number
  code: string
  title: string
  status: InstanceStatus
  round: number
  flow_template_id: number
  flow_template_name: string | null
  flow_version_id: number
  form_version_id: number
  initiator_id: number
  initiator_name: string | null
  initiator_dept_name: string | null
  current_node_keys: string[]
  abnormal: boolean
  pending_count: number
  done_count: number
  my_pending_count: number
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  last_action_at: string | null
  terminated_reason: string | null
}

export interface TaskRow {
  assignment_id: number
  task_id: number
  user_id: number
  status: string
  result: string | null
  seq: number
  is_read: boolean
  read_at: string | null
  acted_at: string | null
  opinion: string | null
  node_key: string | null
  node_name: string | null
  node_type: string | null
  assignee_mode: string | null
  round: number | null
  group_id: string | null
  group_member_count?: number | null
  activated_at: string | null

  instance_id?: number | null
  instance_code?: string | null
  instance_title?: string | null
  instance_status?: InstanceStatus | null
  flow_template_id?: number | null
  flow_template_name?: string | null
  initiator_id?: number | null
  initiator_name?: string | null
  started_at?: string | null
  finished_at?: string | null
  last_action_at?: string | null
}

export interface ProgressAssignee {
  assignment_id: number
  user_id: number
  user_name: string
  status: string
  result: string | null
  is_read: boolean
}

export interface ProgressNode {
  node_id: string
  name: string
  type: string
  type_label: string
  status?: string
  activation_seq?: number
  assignees?: ProgressAssignee[]
  completed_at?: string | null
  /** 并行组 */
  mode?: 'all' | 'any'
  members?: ProgressNode[]
  /** 条件分支 */
  branches?: Array<{
    branch_id: string
    name: string
    is_else: boolean
    /** 实际走的是哪条（PRD F4.2：未走的分支灰显） */
    taken: boolean
    nodes: ProgressNode[]
  }>
}

export interface ActionEntry {
  action_id: number
  action: string
  action_label: string
  node_key: string | null
  node_name: string | null
  actor_id: number
  actor_name: string
  opinion: string | null
  round: number
  from_status: string | null
  to_status: string | null
  changed_fields: Array<{ key: string; label: string; old: unknown; new: unknown }>
  attachments: Array<{ id: number; file_name: string }>
  snapshot_id: number | null
  snapshot_seq: number | null
  created_at: string
}

/** `GET /instances/{id}/render` 的响应 —— 详情页的全部数据。 */
export interface InstanceRender {
  instance: InstanceItem
  my_role: 'CURRENT_HANDLER' | 'INITIATOR' | 'PARTICIPANT' | 'CC' | 'ADMIN'
  assignment: {
    assignment_id: number
    task_id: number
    user_id: number
    status: string
    seq: number
    acted_at: string | null
  } | null
  current_node: {
    node_id: string
    name: string
    type: string
    type_label: string
    assignee_mode: string | null
    opinion_required: boolean
    attachment_required: boolean
  } | null
  schema_data: FormSchema
  values: Record<string, unknown>
  permissions: Record<string, FieldState & { reason?: string }>
  progress: ProgressNode[]
  actions: ActionEntry[]
  allowed_actions: TaskAction[]
  return_targets: Array<{ node_id: string; name: string; type: string }>
  attachments: Array<{
    id: number
    file_name: string
    size_bytes: number
    mime_type: string | null
    is_image: boolean
    url: string
  }>
  snapshot: {
    id: number
    round: number
    seq: number
    kind: string
    created_at: string
  } | null
  ext_fields: ExtFieldItem[]
}

/** 机制 C：运行中追加的动态字段（F5.1）。 */
export interface ExtFieldItem {
  field_key: string
  label: string
  type: string
  required: boolean
  status: string
  editable_node_ids?: string[]
  visible_from_node_id?: string | null
}

export interface ExtFieldPayload {
  label: string
  type: string
  required?: boolean
  /** 可编辑的节点；不给则由服务端取当前待办节点 */
  editable_node_ids?: string[]
  section_key?: string | null
  config?: Record<string, unknown>
  placeholder?: string | null
}

export interface StartOptions {
  flow_template_id: number
  flow_template_name: string
  flow_version_id: number
  flow_version_no: number
  form_version_id: number
  form_version_no: number
  schema_data: FormSchema
  permissions: Record<string, FieldState & { reason?: string }>
  initiator_select_nodes: Array<{
    node_id: string
    node_name: string
    scope_role_ids: number[]
    scope_dept_ids: number[]
  }>
  nodes: ProgressNode[]
}

export interface SubmitPayload {
  data: Record<string, unknown>
  note?: string | null
  attachment_ids?: number[]
  assignee_picks?: Record<string, number[]>
}

export interface ActPayload {
  action: TaskAction
  opinion?: string | null
  attachment_ids?: number[]
  field_patch?: Record<string, unknown>
  return_target?: string | null
  expected_version?: number | null
}

export interface TodoSummary {
  todo: number
  cc_unread: number
  mine_running: number
}

export interface NotificationItem {
  id: number
  type: string
  title: string
  content: string | null
  payload: Record<string, unknown> | null
  link: string | null
  is_read: boolean
  read_at: string | null
  created_at: string
}

// --------------------------------------------------------------------------- 字典

export const INSTANCE_STATUS_META: Record<
  InstanceStatus,
  { text: string; color: string }
> = {
  DRAFT: { text: '草稿', color: 'default' },
  RUNNING: { text: '审批中', color: 'processing' },
  REJECTED: { text: '已驳回', color: 'error' },
  APPROVED: { text: '已通过', color: 'success' },
  WITHDRAWN: { text: '已撤回', color: 'default' },
  TERMINATED: { text: '已终止', color: 'error' },
}

export const ACTION_LABELS: Record<TaskAction, string> = {
  AGREE: '同意',
  REJECT: '驳回',
  RETURN: '退回',
  SUBMIT: '提交',
}

export const NODE_STATUS_META: Record<string, { text: string; color: string }> = {
  PENDING: { text: '未开始', color: 'default' },
  ACTIVE: { text: '进行中', color: 'processing' },
  COMPLETED: { text: '已完成', color: 'success' },
  CANCELLED: { text: '已取消', color: 'default' },
}

export const MY_ROLE_LABELS: Record<string, string> = {
  CURRENT_HANDLER: '待你处理',
  INITIATOR: '我是发起人',
  PARTICIPANT: '我参与过',
  CC: '我被抄送',
  ADMIN: '管理员视角',
}

export const NOTIF_TYPE_LABELS: Record<string, string> = {
  TASK_CREATED: '新待办',
  TASK_CANCELLED: '待办取消',
  INSTANCE_APPROVED: '已通过',
  INSTANCE_REJECTED: '被驳回',
  INSTANCE_RETURNED: '被退回',
  INSTANCE_WITHDRAWN: '已撤回',
  INSTANCE_TERMINATED: '已终止',
  CC_RECEIVED: '抄送',
  ABNORMAL_ASSIGN: '分配异常',
  EXT_FIELD_ADDED: '新增字段',
}

/**
 * 消息标签的颜色。按类型映射成固定表 ——
 * 用 `type.includes('REJECT')` 这类子串匹配，新增类型时会悄悄落到 default。
 */
const NOTIF_TYPE_COLORS: Record<string, string> = {
  TASK_CREATED: 'blue',
  TASK_CANCELLED: 'default',
  INSTANCE_APPROVED: 'green',
  INSTANCE_REJECTED: 'red',
  INSTANCE_RETURNED: 'orange',
  INSTANCE_WITHDRAWN: 'default',
  INSTANCE_TERMINATED: 'red',
  CC_RECEIVED: 'cyan',
  ABNORMAL_ASSIGN: 'red',
  EXT_FIELD_ADDED: 'purple',
}

export function notifColor(type: string): string {
  return NOTIF_TYPE_COLORS[type] ?? 'default'
}
