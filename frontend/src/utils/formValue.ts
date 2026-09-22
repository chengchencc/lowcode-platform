/**
 * 表单取值/展示/校验的公共逻辑。
 *
 * 后端 `form_schema.py` 是结构的权威；本模块只做**展示与即时提示**。
 * 真正的提交校验在服务端（前端校验可被绕过，不是安全边界）。
 */

import dayjs from 'dayjs'

import type { FieldDef, FieldOption, FormSchema, FieldState } from '@/types/form'
import { OPTION_FIELD_TYPES } from '@/types/form'

/** 多值控件（用数组存储）。与后端 MULTI_VALUE_FIELD_TYPES 一致。 */
const MULTI_TYPES = new Set(['checkbox', 'user_multi', 'dept_multi', 'image'])

export function isMultiValue(field: FieldDef): boolean {
  return MULTI_TYPES.has(field.type)
}

export function optionLabel(field: FieldDef, value: unknown): string {
  const options: FieldOption[] = field.options ?? []
  const hit = options.find((o) => String(o.value) === String(value))
  return hit ? hit.label : String(value ?? '')
}

/**
 * 把值渲染成人读的文本（只读态用）。
 * `lookup` 供人员/部门控件把 id 换成名字 —— 那两个控件的值不是自解释的。
 */
export function formatValue(
  field: FieldDef,
  value: unknown,
  lookup?: (kind: 'user' | 'dept', id: number | string) => string,
): string {
  if (value === null || value === undefined || value === '') return '—'

  switch (field.type) {
    case 'switch':
      return value ? '是' : '否'

    case 'checkbox':
    case 'radio':
    case 'select':
      if (Array.isArray(value)) return value.map((v) => optionLabel(field, v)).join('、')
      return optionLabel(field, value)

    case 'date':
      return dayjs(String(value)).isValid() ? dayjs(String(value)).format('YYYY-MM-DD') : String(value)
    case 'time':
      return String(value)
    case 'datetime':
      return dayjs(String(value)).isValid()
        ? dayjs(String(value)).format('YYYY-MM-DD HH:mm')
        : String(value)

    case 'user':
    case 'user_multi':
      return idsToText(value, (id) => lookup?.('user', id) ?? `#${id}`)
    case 'dept':
    case 'dept_multi':
      return idsToText(value, (id) => lookup?.('dept', id) ?? `#${id}`)

    case 'attachment':
    case 'image': {
      const list = Array.isArray(value) ? value : [value]
      return list.length ? `${list.length} 个文件` : '—'
    }

    default:
      return String(value)
  }
}

function idsToText(value: unknown, map: (id: number | string) => string): string {
  const list = Array.isArray(value) ? value : [value]
  if (!list.length) return '—'
  return list.map(map).join('、')
}

/** 取字段默认值；多值控件给空数组而不是 null，避免绑定时报错。 */
export function defaultValueOf(field: FieldDef): unknown {
  if (field.default_value !== undefined && field.default_value !== null) {
    return field.default_value
  }
  if (isMultiValue(field)) return []
  if (field.type === 'subtable') return []
  if (field.type === 'switch') return false
  return undefined
}

/** 用 schema 的默认值初始化一份数据。 */
export function buildInitialValues(schema: FormSchema): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  for (const section of schema.sections) {
    for (const field of section.fields) {
      const def = defaultValueOf(field)
      if (def !== undefined) values[field.key] = def
      if (field.type === 'subtable') {
        values[field.key] = (values[field.key] as unknown[]) ?? []
      }
    }
  }
  return values
}

// --------------------------------------------------------------------------- 校验

export interface ValueIssue {
  key: string
  label: string
  message: string
}

/**
 * 客户端即时校验。规则与后端 `form_schema.FieldValidators` 对应，
 * **但不是安全边界** —— 提交时服务端会重新校验一遍。
 */
export function validateValues(
  schema: FormSchema,
  values: Record<string, unknown>,
  states: Record<string, FieldState>,
): ValueIssue[] {
  const issues: ValueIssue[] = []

  const checkField = (field: FieldDef, value: unknown, statePath: string) => {
    const state = states[statePath]
    if (!state?.visible) return

    const empty =
      value === null ||
      value === undefined ||
      value === '' ||
      (Array.isArray(value) && value.length === 0)

    if (state.required && empty) {
      issues.push({ key: statePath, label: field.label, message: `请填写${field.label}` })
      return
    }
    if (empty) return

    const v = field.validators ?? {}

    if (field.type === 'text' || field.type === 'textarea') {
      const text = String(value)
      if (v.min_length != null && text.length < v.min_length) {
        issues.push({ key: statePath, label: field.label, message: `至少 ${v.min_length} 个字符` })
      }
      if (v.max_length != null && text.length > v.max_length) {
        issues.push({ key: statePath, label: field.label, message: `最多 ${v.max_length} 个字符` })
      }
      if (v.regex) {
        try {
          if (!new RegExp(`^(?:${v.regex})$`).test(text)) {
            issues.push({ key: statePath, label: field.label, message: `${field.label}格式不正确` })
          }
        } catch {
          // 设计器里的正则可能还没写对，此时不打扰填写者
        }
      }
    }

    if (field.type === 'number') {
      const num = Number(value)
      if (Number.isNaN(num)) {
        issues.push({ key: statePath, label: field.label, message: `${field.label}必须是数字` })
      } else {
        if (v.min != null && num < v.min) {
          issues.push({ key: statePath, label: field.label, message: `不能小于 ${v.min}` })
        }
        if (v.max != null && num > v.max) {
          issues.push({ key: statePath, label: field.label, message: `不能大于 ${v.max}` })
        }
      }
    }

    if (field.type === 'subtable') {
      const rows = Array.isArray(value) ? value : []
      if (v.min_rows != null && rows.length < v.min_rows) {
        issues.push({ key: statePath, label: field.label, message: `至少 ${v.min_rows} 行` })
      }
      if (v.max_rows != null && rows.length > v.max_rows) {
        issues.push({ key: statePath, label: field.label, message: `最多 ${v.max_rows} 行` })
      }
      rows.forEach((row, index) => {
        for (const col of field.columns ?? []) {
          const cell = (row as Record<string, unknown>)[col.key]
          const cellEmpty =
            cell === null || cell === undefined || cell === '' ||
            (Array.isArray(cell) && cell.length === 0)
          if (col.required && !col.formula && cellEmpty) {
            issues.push({
              key: `${statePath}[].${col.key}`,
              label: col.label,
              message: `第 ${index + 1} 行的「${col.label}」未填写`,
            })
          }
        }
      })
    }

    if (field.type === 'attachment' || field.type === 'image') {
      const list = Array.isArray(value) ? value : [value]
      if (v.max_file_count != null && list.length > v.max_file_count) {
        issues.push({
          key: statePath,
          label: field.label,
          message: `最多上传 ${v.max_file_count} 个文件`,
        })
      }
    }
  }

  for (const section of schema.sections) {
    for (const field of section.fields) {
      checkField(field, values[field.key], field.key)
    }
  }

  return issues
}

/** 级联下拉：由父字段的值决定本字段的候选选项。 */
export function cascaderOptions(field: FieldDef, values: Record<string, unknown>): FieldOption[] {
  const parent = field.cascader?.parent_field
  if (!parent) return []
  const key = String(values[parent] ?? '')
  return field.cascader?.options_by_parent?.[key] ?? []
}

export { OPTION_FIELD_TYPES }
