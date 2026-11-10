/**
 * 设计器编辑 schema 时的构造与规范化工具。
 *
 * 为什么需要 `normalizeField`：服务端允许 `formula` / `cascader` 为 null
 * （非公式字段就是 null），但属性面板在切到「公式」类型后会直接读
 * `field.formula.type` —— 不先补齐就会在运行时炸。所有会改 `type` 的地方
 * 都要过一遍这里。
 */

import type {
  DisplayConfig,
  FieldDef,
  FieldType,
  FormSchema,
  SectionDef,
  SectionStage,
} from '@/types/form'
import {
  DISPLAY_FIELD_TYPES,
  FIELD_TYPE_LABELS,
  OPTION_FIELD_TYPES,
} from '@/types/form'

/** 需要子表列的类型 */
const NEEDS_COLUMNS: FieldType[] = ['subtable']
/** 需要 formula 对象的类型 */
const NEEDS_FORMULA: FieldType[] = ['formula']
/** 需要 cascader 对象的类型 */
const NEEDS_CASCADER: FieldType[] = ['cascader']

function defaultDisplay(type: FieldType): DisplayConfig {
  switch (type) {
    case 'heading':
      return { text: '标题', level: 2 }
    case 'paragraph':
      return { text: '说明文字' }
    case 'divider':
      return { text: '' }
    case 'image_view':
      return { url: '', alt: '' }
    case 'rich_text':
      return { markdown: '说明文字' }
    default:
      return {}
  }
}

/** 按类型补齐字段的各个可选结构，避免属性面板读到 null。 */
export function normalizeField(field: FieldDef): FieldDef {
  field.validators ??= {}
  field.options ??= []
  field.columns ??= []

  if (DISPLAY_FIELD_TYPES.includes(field.type)) {
    // 展示控件不绑定数据：清掉数据属性，属性面板只保留展示配置
    field.required = false
    field.options = []
    field.validators = {}
    field.formula = null
    field.cascader = null
    field.columns = []
    field.default_value = null
    field.display ??= defaultDisplay(field.type)
    return field
  }

  // 从展示控件切回数据控件时清掉展示配置
  field.display = null

  if (NEEDS_FORMULA.includes(field.type)) {
    field.formula ??= { type: 'arithmetic', expression: '' }
    // 公式字段的值由计算得出，必填没有意义
    field.required = false
  }
  if (NEEDS_CASCADER.includes(field.type)) {
    field.cascader ??= { parent_field: '', options_by_parent: {} }
  }
  if (!NEEDS_COLUMNS.includes(field.type) && field.columns.length === 0) {
    field.columns = []
  }
  return field
}

/** 生成一个在本层内不重复的 key。 */
export function uniqueKey(existing: Iterable<string>, prefix: string): string {
  const used = new Set(existing)
  if (!used.has(prefix)) return prefix
  let n = 2
  while (used.has(`${prefix}_${n}`)) n += 1
  return `${prefix}_${n}`
}

function collectKeys(schema: FormSchema): string[] {
  const keys: string[] = []
  for (const section of schema.sections) {
    keys.push(section.key)
    for (const field of section.fields) {
      keys.push(field.key)
      for (const col of field.columns ?? []) keys.push(col.key)
    }
  }
  return keys
}

export function makeField(schema: FormSchema, type: FieldType, label?: string): FieldDef {
  const key = uniqueKey(collectKeys(schema), type === 'formula' ? 'calc' : type)
  const display = DISPLAY_FIELD_TYPES.includes(type)
  return normalizeField({
    key,
    label: label ?? (display ? FIELD_TYPE_LABELS[type] : key),
    type,
    sort: 0,
    required: false,
    visible_at_start: true,
  })
}

export function makeColumn(subtable: FieldDef, type: FieldType = 'text'): FieldDef {
  const key = uniqueKey(
    (subtable.columns ?? []).map((c) => c.key),
    'col',
  )
  return normalizeField({
    key,
    label: key,
    type,
    sort: (subtable.columns?.length ?? 0) + 1,
    required: false,
  })
}

export function makeSection(schema: FormSchema, stage: SectionStage = 'apply'): SectionDef {
  const key = uniqueKey(
    schema.sections.map((s) => s.key),
    'sec',
  )
  return { key, title: '新分区', stage, sort: schema.sections.length + 1, fields: [] }
}

/** 同层内重排：把 index 处的元素移动 delta 位。返回是否真的移动了。 */
export function moveInArray<T>(list: T[], index: number, delta: number): boolean {
  const target = index + delta
  if (target < 0 || target >= list.length) return false
  const [item] = list.splice(index, 1)
  list.splice(target, 0, item)
  return true
}

/** 按 sort 重排并回写 sort 值，保持与后端的排序语义一致。 */
export function resequence(list: Array<{ sort?: number }>): void {
  list.forEach((item, index) => {
    item.sort = index + 1
  })
}

/** 该控件类型是否需要用户配置选项。 */
export function typeNeedsOptions(type: FieldType): boolean {
  return OPTION_FIELD_TYPES.includes(type)
}

/** 删除字段时清理引用它的公式，避免留下必然报错的配置。 */
export function stripFormulaRefs(schema: FormSchema, removedKey: string): string[] {
  const cleaned: string[] = []
  const allFields: FieldDef[] = []
  for (const section of schema.sections) {
    for (const field of section.fields) {
      allFields.push(field, ...(field.columns ?? []))
    }
  }

  for (const field of allFields) {
    const f = field.formula
    if (!f) continue
    if (f.expression && new RegExp(`\\b${removedKey}\\b`).test(f.expression)) {
      f.expression = f.expression.replace(new RegExp(`\\b${removedKey}\\b`, 'g'), '')
      cleaned.push(`${field.label} 的表达式`)
    }
    if (f.start_field === removedKey) f.start_field = null
    if (f.end_field === removedKey) f.end_field = null
    if (f.subtable_key === removedKey) {
      f.subtable_key = null
      f.column_key = null
      cleaned.push(`${field.label} 的子表合计`)
    }
  }
  return cleaned
}
