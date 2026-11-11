/**
 * 表单取值/展示/校验的公共逻辑。
 *
 * 后端 `form_schema.py` 是结构的权威；本模块只做**展示与即时提示**。
 * 真正的提交校验在服务端（前端校验可被绕过，不是安全边界）。
 */

import dayjs from 'dayjs'

import type { FieldDef, FieldOption, FormSchema, FieldState } from '@/types/form'
import { DISPLAY_FIELD_TYPES, OPTION_FIELD_TYPES } from '@/types/form'

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
      if (DISPLAY_FIELD_TYPES.includes(field.type)) continue
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

    checkOptionMembership(field, value, statePath, issues)
    checkCascader(field, value, values, statePath, issues, field.label)
  }

  for (const section of schema.sections) {
    for (const field of section.fields) {
      if (DISPLAY_FIELD_TYPES.includes(field.type)) continue
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

/**
 * 取值必须在已配选项里（单选取单值，复选取全部）。
 *
 * 没配选项的控件不做限制 —— 设计器允许先建字段后补选项。
 */
function checkOptionMembership(
  field: FieldDef,
  value: unknown,
  statePath: string,
  issues: ValueIssue[],
): void {
  const options = field.options ?? []
  if (!options.length) return
  if (field.type !== 'select' && field.type !== 'radio' && field.type !== 'checkbox') return

  const picked = Array.isArray(value) ? value : [value]
  const allowed = new Set(options.map((o) => String(o.value)))
  if (picked.every((item) => allowed.has(String(item)))) return

  issues.push({
    key: statePath,
    label: field.label,
    message: field.label + '的取值不在选项里',
  })
}

/**
 * 级联下拉的值要跟父字段的当前值对得上（PRD §3.2.2）。
 *
 * 与服务端 `app/engine/value_rules.py` 的 `_check_cascader` 同一套判定 ——
 * 前端先提示，服务端才是边界。
 */
function checkCascader(
  field: FieldDef,
  value: unknown,
  values: Record<string, unknown>,
  statePath: string,
  issues: ValueIssue[],
  label: string,
): void {
  if (field.type !== 'cascader' || !field.cascader) return
  const parent = field.cascader.parent_field
  const parentValue = values[parent]
  if (parentValue === null || parentValue === undefined || parentValue === '') {
    issues.push({ key: statePath, label, message: `请先选择${label}的上级选项` })
    return
  }
  const options = cascaderOptions(field, values)
  if (!options.length) {
    issues.push({ key: statePath, label, message: `${label}在上级选项下没有可选值` })
    return
  }
  if (!options.some((o) => String(o.value) === String(value))) {
    issues.push({ key: statePath, label, message: `${label}与上级选项不匹配` })
  }
}

/**
 * 父字段改了 → 子级联字段里对不上的旧值清掉。
 *
 * 不清的后果是脏数据：「费用类别」从差旅改成办公，「费用明细」还停在「机票」，
 * 提交时被服务端拦下，用户还得自己想起去改那一个下拉。
 * 返回**新对象**（没变化时返回原对象，避免无谓的重渲染）。
 */
export function clearStaleCascades(
  schema: FormSchema,
  values: Record<string, unknown>,
  changedKey: string,
): Record<string, unknown> {
  /** `owner` 是取值的作用域：顶层字段是表单值，子表列是**同一行**。 */
  const isStale = (field: FieldDef, owner: Record<string, unknown>): boolean => {
    const config = field.cascader
    if (field.type !== 'cascader' || config?.parent_field !== changedKey) return false
    const current = owner[field.key]
    if (current === null || current === undefined || current === '') return false

    const parentValue = owner[config.parent_field]
    const options =
      parentValue === null || parentValue === undefined || parentValue === ''
        ? []
        : config.options_by_parent?.[String(parentValue)] ?? []
    return !options.some((o) => String(o.value) === String(current))
  }

  let next = values
  for (const section of schema.sections) {
    for (const field of section.fields) {
      if (field.type === 'subtable') {
        const rows = Array.isArray(values[field.key]) ? (values[field.key] as unknown[]) : []
        let touched = false
        const newRows = rows.map((row) => {
          let newRow = row as Record<string, unknown>
          for (const column of field.columns ?? []) {
            if (isStale(column, newRow)) {
              newRow = { ...newRow, [column.key]: null }
              touched = true
            }
          }
          return newRow
        })
        if (touched) next = { ...next, [field.key]: newRows }
        continue
      }
      if (isStale(field, next)) next = { ...next, [field.key]: null }
    }
  }

  return next
}

export { OPTION_FIELD_TYPES }
