/**
 * 表单 schema 的 TS 类型。
 *
 * **必须与 `backend/app/schemas/form_schema.py` 保持一致** ——
 * 那是唯一的权威定义，这里是它的镜像。改一边就要改另一边。
 * 命名全链路 snake_case（决策 D10）。
 *
 * 字段 key 的引用记法：
 * - 顶层字段：`amount`
 * - 子表列：  `items[].amount`
 */

import type { ConditionGroup } from '@/types/conditions'

export type SectionStage = 'apply' | 'approve' | 'supplement' | 'archive'

export type FieldType =
  // 基础
  | 'text'
  | 'textarea'
  | 'number'
  | 'radio'
  | 'checkbox'
  | 'select'
  | 'date'
  | 'time'
  | 'datetime'
  | 'switch'
  // 组织
  | 'user'
  | 'user_multi'
  | 'dept'
  | 'dept_multi'
  // 文件
  | 'attachment'
  | 'image'
  // 子表
  | 'subtable'
  // 增强
  | 'formula'
  | 'cascader'
  // 展示（不绑定数据）
  | 'heading'
  | 'paragraph'
  | 'divider'
  | 'image_view'
  | 'rich_text'

export type FormulaType = 'arithmetic' | 'subtable_sum' | 'date_diff' | 'concat'

export interface FieldOption {
  label: string
  value: string | number | boolean
}

export interface FieldValidators {
  min_length?: number | null
  max_length?: number | null
  regex?: string | null
  min?: number | null
  max?: number | null
  precision?: number | null
  min_rows?: number | null
  max_rows?: number | null
  max_file_count?: number | null
  max_file_size_mb?: number | null
}

export interface CascaderConfig {
  parent_field: string
  options_by_parent: Record<string, FieldOption[]>
}

export interface FieldFormula {
  type: FormulaType
  expression?: string | null
  subtable_key?: string | null
  column_key?: string | null
  start_field?: string | null
  end_field?: string | null
  unit?: 'days'
}

export interface DisplayConfig {
  text?: string | null
  /** 仅 heading */
  level?: 1 | 2 | 3
  /** 仅 image_view */
  url?: string | null
  alt?: string | null
  /** 仅 rich_text */
  markdown?: string | null
}

export interface FieldDef {
  key: string
  label: string
  type: FieldType
  sort?: number
  required?: boolean
  placeholder?: string | null
  help?: string | null
  default_value?: unknown
  options?: FieldOption[]
  validators?: FieldValidators
  /** true=发起阶段可编辑；false=发起阶段隐藏，由流程节点显式打开（F5.4） */
  visible_at_start?: boolean
  /** 栅格宽度（24 栅格制）；缺省按列数与控件类型自动决定 */
  span?: number | null
  /** 展示型控件配置 */
  display?: DisplayConfig | null
  formula?: FieldFormula | null
  cascader?: CascaderConfig | null
  /** 仅 type=subtable */
  columns?: FieldDef[]
}

export interface SectionDef {
  key: string
  title: string
  stage?: SectionStage
  sort?: number
  description?: string | null
  collapsible?: boolean
  /** 分区级列数覆盖；缺省跟随表单 layout.columns */
  columns?: 1 | 2 | 3 | 4 | null
  fields: FieldDef[]
}

export interface FormLayout {
  label_position?: 'top' | 'left'
  columns?: 1 | 2 | 3 | 4
}

export type RuleEffectType = 'hidden' | 'readonly' | 'required'

export interface RuleEffect {
  target: string
  effect: RuleEffectType
}

export interface FormRule {
  id: string
  name?: string | null
  when: ConditionGroup
  effects: RuleEffect[]
  /** 规则把字段隐藏时是否清空值 */
  clear_when_hidden?: boolean
}

export interface FormSchema {
  model_version?: number
  layout?: FormLayout
  sections: SectionDef[]
  rules?: FormRule[]
  /** 用哪个表单字段作为实例标题；不配置则用流程模板名 */
  title_field?: string | null
}

// --------------------------------------------------------------------------- 渲染三态

/** 渲染模式：编辑 / 只读 / 预览（设计器内）。M3 会增加「权限态」。 */
export type RenderMode = 'edit' | 'readonly' | 'preview'

/**
 * 单个字段的三态。渲染器只消费它，不自己推导权限 ——
 * M2 由 `useFieldState` 从 schema 推出，M3 起改由服务端权限矩阵下发。
 */
export interface FieldState {
  visible: boolean
  editable: boolean
  required: boolean
}

// --------------------------------------------------------------------------- 校验

export interface SchemaIssue {
  code: string
  message: string
  path?: string
  severity: 'error' | 'warning'
}

// --------------------------------------------------------------------------- API DTO

export type FormStatus = 'DRAFT' | 'PUBLISHED' | 'DISABLED'
export type FormVersionStatus = 'DRAFT' | 'PUBLISHED' | 'ARCHIVED'

export interface FormTemplate {
  id: number
  name: string
  code: string | null
  group_name: string | null
  icon: string | null
  status: FormStatus
  description: string | null
  current_version_id: number | null
  current_version_no: number | null
  draft_version_id: number | null
  version_count: number
  field_count: number
  created_by: number | null
  created_at: string | null
  updated_at: string | null
}

export interface FormTemplateInput {
  name: string
  code?: string | null
  group_name?: string | null
  icon?: string | null
  description?: string | null
  schema_data?: FormSchema
}

export interface FormVersionBrief {
  id: number
  template_id: number
  version_no: number
  status: FormVersionStatus
  remark: string | null
  created_by: number | null
  published_at: string | null
  created_at: string | null
}

export interface FormVersion extends FormVersionBrief {
  schema_data: FormSchema
  referenced_by_flows: Array<Record<string, unknown>>
}

export interface FormValidateResult {
  valid: boolean
  errors: SchemaIssue[]
  warnings: SchemaIssue[]
}

export interface FormPreviewField {
  key: string
  label: string
  type: string
  computed: unknown
}

export interface FormPreview {
  version_id: number
  template_id: number
  schema_data: FormSchema
  sample_data: Record<string, unknown>
  computed_fields: FormPreviewField[]
}

export interface AttachmentInfo {
  id: number
  file_name: string
  size_bytes: number
  mime_type: string | null
  is_image: boolean
  uploader_id: number
  created_at: string
  url: string
}

// --------------------------------------------------------------------------- 控件字典

/** 控件类型的中文名，设计器与渲染器共用。 */
export const FIELD_TYPE_LABELS: Record<FieldType, string> = {
  text: '单行文本',
  textarea: '多行文本',
  number: '数字',
  radio: '单选',
  checkbox: '复选',
  select: '下拉',
  date: '日期',
  time: '时间',
  datetime: '日期时间',
  switch: '开关',
  user: '人员选择',
  user_multi: '人员多选',
  dept: '部门选择',
  dept_multi: '部门多选',
  attachment: '附件上传',
  image: '图片上传',
  subtable: '明细子表',
  formula: '公式',
  cascader: '级联下拉',
  heading: '标题',
  paragraph: '说明文字',
  divider: '分割线',
  image_view: '图片展示',
  rich_text: '富文本说明',
}

/** 设计器左侧控件面板的分组（PRD §3.2.2）。 */
export const FIELD_TYPE_GROUPS: Array<{ title: string; types: FieldType[] }> = [
  {
    title: '基础',
    types: ['text', 'textarea', 'number', 'radio', 'checkbox', 'select', 'date', 'time', 'datetime', 'switch'],
  },
  { title: '组织', types: ['user', 'user_multi', 'dept', 'dept_multi'] },
  { title: '文件', types: ['attachment', 'image'] },
  { title: '子表', types: ['subtable'] },
  { title: '增强', types: ['formula', 'cascader'] },
  { title: '展示', types: ['heading', 'paragraph', 'divider', 'image_view', 'rich_text'] },
]

/** 展示型控件：不绑定实例数据，不进入权限矩阵的编辑项。 */
export const DISPLAY_FIELD_TYPES: FieldType[] = [
  'heading', 'paragraph', 'divider', 'image_view', 'rich_text',
]

export function isDisplayField(field: FieldDef): boolean {
  return DISPLAY_FIELD_TYPES.includes(field.type)
}

/** 子表行内允许的控件（与后端 SUBTABLE_COLUMN_TYPES 一致）。 */
export const SUBTABLE_COLUMN_TYPES: FieldType[] = [
  'text', 'textarea', 'number', 'radio', 'checkbox', 'select',
  'date', 'time', 'datetime', 'switch',
  'user', 'user_multi', 'dept', 'dept_multi',
  'attachment', 'image', 'formula',
]

/** 需要配置选项的控件 */
export const OPTION_FIELD_TYPES: FieldType[] = ['radio', 'checkbox', 'select']

export const SECTION_STAGE_LABELS: Record<SectionStage, string> = {
  apply: '申请区',
  approve: '审批区',
  supplement: '补充区',
  archive: '归档区',
}

export const SECTION_STAGE_HINTS: Record<SectionStage, string> = {
  apply: '发起人填写；后续审批节点默认只读',
  approve: '审批过程中填写',
  supplement: '默认对所有节点隐藏，由流程节点显式打开（补充字段）',
  archive: '归档展示用',
}
