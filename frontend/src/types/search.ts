/** 实例业务字段检索（M13）。 */

export type FilterKind =
  | 'text'
  | 'number'
  | 'date'
  | 'time'
  | 'datetime'
  | 'bool'
  | 'option'
  | 'multi_option'
  | 'user'
  | 'user_multi'
  | 'dept'
  | 'dept_multi'

export interface SearchFieldConfig {
  field_key: string
  label: string
  field_type: string
  filter_kind: FilterKind
  options: Array<string | number | boolean>
  start_visible: boolean
  selected: boolean
  indexed_at: string | null
}

export interface SearchFieldMeta {
  field_key: string
  label: string
  filter_kind: FilterKind
  options: Array<string | number | boolean>
  start_visible: boolean
}

export interface SearchFilter {
  field: string
  op: string
  value?: unknown
}
