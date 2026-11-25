/**
 * 流程定义的 TS 类型。
 *
 * **必须与 `backend/app/schemas/flow_definition.py` 保持一致** ——
 * 那是唯一的权威定义，这里是它的镜像。改一边就要改另一边。
 * 命名全链路 snake_case（决策 D10）。
 */

export type NodeType = 'start' | 'approval' | 'fill' | 'parallel' | 'condition' | 'cc' | 'end'

export type AssigneeMode = 'SINGLE' | 'SEQUENTIAL' | 'ALL' | 'ANY'

export type PermMode = 'hidden' | 'readonly' | 'editable' | 'editable-required'

export type AssigneeSourceType =
  | 'user'
  | 'role'
  | 'dept_manager'
  | 'form_user_field'
  | 'form_dept_field'
  | 'initiator_select'
  | 'prev_node_actors'

export type RejectPolicy = 'reject_to_initiator' | 'reject_forbidden'

/** 运行中实例里，已办处理人再次打开时的字段范围（终态仍按归档视角）。 */
export type HistoryView = 'own_nodes' | 'full' | 'start'

// --------------------------------------------------------------------------- 条件

import type { Comparison, ConditionGroup } from '@/types/conditions'

export type { Comparison, Condition, ConditionGroup } from '@/types/conditions'
export { isConditionGroup } from '@/types/conditions'

// --------------------------------------------------------------------------- 审批人

export interface AssigneeSource {
  type: AssigneeSourceType
  user_ids?: number[]
  role_ids?: number[]
  dept_ids?: number[]
  dept_field?: string | null
  field?: string | null
  scope_role_ids?: number[]
  scope_dept_ids?: number[]
  node_id?: string | null
}

export interface AssigneeRule {
  mode: AssigneeMode
  sources: AssigneeSource[]
  on_empty?: 'to_admin' | 'block_publish'
  initiator_select?: AssigneeSource | null
}

// --------------------------------------------------------------------------- 字段权限

export interface ConditionalOverride {
  when: ConditionGroup
  field_key: string
  mode: PermMode
}

export interface FieldPermissionRule {
  base: PermMode
  partitions: Record<string, PermMode>
  overrides: Record<string, PermMode>
  conditional_overrides: ConditionalOverride[]
}

// --------------------------------------------------------------------------- 节点

interface NodeBase {
  id: string
  name: string
}

export interface ApprovalNode extends NodeBase {
  type: 'approval'
  assignee: AssigneeRule
  reject_policy: RejectPolicy
  /** null = 允许退回全部前序；[] = 禁止退回；["s1"] = 白名单 */
  return_targets: string[] | null
  timeout_hours: number | null
  opinion_required: boolean
  attachment_required: boolean
  fields_permission: FieldPermissionRule
}

export interface FillNode extends NodeBase {
  type: 'fill'
  assignee: AssigneeRule
  return_targets: string[] | null
  timeout_hours: number | null
  fields_permission: FieldPermissionRule
}

export interface ParallelNode extends NodeBase {
  type: 'parallel'
  mode: 'all' | 'any'
  members: Array<ApprovalNode | FillNode>
}

export interface Branch {
  id: string
  name?: string | null
  /** null 即「否则」分支 */
  when: ConditionGroup | null
  steps: StepNode[]
}

export interface ConditionNode extends NodeBase {
  type: 'condition'
  branches: Branch[]
}

export interface CcNode extends NodeBase {
  type: 'cc'
  cc_to: AssigneeRule
  allow_read: boolean
}

export type StepNode = ApprovalNode | FillNode | ParallelNode | ConditionNode | CcNode

export interface StartNode extends NodeBase {
  type: 'start'
  /** null = 用 L0 默认语义（visible_at_start ? editable : hidden） */
  fields_permission: FieldPermissionRule | null
}

export interface EndNode extends NodeBase {
  type: 'end'
}

export interface FlowDefinition {
  model_version: number
  /** 已办处理人打开运行中实例时的字段范围；旧版定义可能没有，按默认值处理 */
  history_view?: HistoryView
  /**
   * 防自审开关（流程级）：默认开启，角色/部门/指定人员等来源剔除发起人；
   * 关闭后允许解析到发起人。旧版定义可能没有，按开启处理。
   */
  prevent_self_approval?: boolean
  start: StartNode
  steps: StepNode[]
  end: EndNode
}

// --------------------------------------------------------------------------- API DTO

export type FlowStatus = 'DRAFT' | 'PUBLISHED' | 'DISABLED'
export type FlowVersionStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'

export interface FlowTemplate {
  id: number
  name: string
  code: string | null
  category: string | null
  status: FlowStatus
  description: string | null
  form_template_id: number
  form_template_name: string | null
  initiator_scope: InitiatorScope
  current_version_id: number | null
  current_version_no: number | null
  locked_form_version_id: number | null
  locked_form_version_no: number | null
  draft_version_id: number | null
  version_count: number
  node_count: number
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

/** 流程配置导出/导入载荷（F2.9）。导出 JSON 加 `form_template_id` 后可回传导入。 */
export interface FlowTemplateExport {
  name: string
  code: string | null
  category: string | null
  description: string | null
  initiator_scope: InitiatorScope
  /** 源环境绑定的表单，仅作人工识别；导入时按目标环境重新选择 */
  form_name: string | null
  form_code: string | null
  definition: FlowDefinition
}

export interface InitiatorScope {
  type: 'all' | 'role' | 'dept'
  role_ids?: number[]
  dept_ids?: number[]
}

export interface FlowVersionBrief {
  id: number
  template_id: number
  version_no: number
  status: FlowVersionStatus
  remark: string | null
  locked_form_version_id: number
  locked_form_version_no: number | null
  created_by: number | null
  published_at: string | null
  created_at: string | null
}

export interface FlowVersion extends FlowVersionBrief {
  definition: FlowDefinition
  validation_report: Record<string, unknown> | null
}

/** 与后端 engine/validate.py 的 ValidationIssue 对应 */
export interface FlowValidationIssue {
  code: string
  message: string
  node_id?: string | null
  path?: string
  severity: 'error' | 'warning'
}

export interface FlowValidateResult {
  valid: boolean
  errors: FlowValidationIssue[]
  warnings: FlowValidationIssue[]
}

export interface ReturnTarget {
  id: string
  name: string
  type: string
}

// --------------------------------------------------------------------------- 字典

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  start: '发起',
  approval: '审批',
  fill: '填写',
  parallel: '并行组',
  condition: '条件分支',
  cc: '抄送',
  end: '结束',
}

export const ASSIGNEE_MODE_LABELS: Record<AssigneeMode, string> = {
  SINGLE: '单人',
  SEQUENTIAL: '多人依次',
  ALL: '并行会签（全部同意）',
  ANY: '并行或签（任一同意）',
}

export const ASSIGNEE_SOURCE_LABELS: Record<AssigneeSourceType, string> = {
  user: '指定人员',
  role: '指定角色',
  dept_manager: '部门主管',
  form_user_field: '表单人员字段',
  form_dept_field: '表单部门字段',
  initiator_select: '发起人指定',
  prev_node_actors: '上一节点处理人',
}

export const PERM_MODE_LABELS: Record<PermMode, string> = {
  hidden: '隐藏',
  readonly: '只读',
  editable: '可编辑',
  'editable-required': '可编辑且必填',
}

export const PERM_MODE_COLORS: Record<PermMode, string> = {
  hidden: 'default',
  readonly: 'blue',
  editable: 'green',
  'editable-required': 'orange',
}

export const COMPARISON_LABELS: Record<Comparison, string> = {
  '==': '等于',
  '!=': '不等于',
  '>': '大于',
  '>=': '大于等于',
  '<': '小于',
  '<=': '小于等于',
  in: '属于',
  not_in: '不属于',
  contains: '包含',
  is_empty: '为空',
  is_not_empty: '不为空',
}

/** 「否则」分支的固定 id 前缀，供前端生成唯一标识用 */
export const ELSE_BRANCH_ID = 'else'
