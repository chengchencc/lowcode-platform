/**
 * 把实例字段值渲染成人能读的文本（处理历史 / 快照对照）。
 *
 * 表单值里存的是 option value、人员/部门 id、附件 id —— 直接 String()
 * 出来就是一串 code。这里按 schema 的字段类型换成选项标签、姓名、
 * 部门名和文件名；查不到时再退回原值，避免静默丢信息。
 */

import type { FieldDef, FormSchema } from '@/types/form'
import { formatValue } from '@/utils/formValue'

export interface ValueLookups {
  userName?: (id: number) => string
  deptName?: (id: number) => string
  attachmentName?: (id: number) => string | undefined
}

/** 字段引用 → 字段定义。子表列同时收录 `a[].b` 与 `a.b` 两种写法。 */
export function buildFieldIndex(schema?: FormSchema | null): Map<string, FieldDef> {
  const out = new Map<string, FieldDef>()
  for (const section of schema?.sections ?? []) {
    for (const field of section.fields) {
      out.set(field.key, field)
      for (const column of field.columns ?? []) {
        out.set(`${field.key}[].${column.key}`, column)
        out.set(`${field.key}.${column.key}`, column)
      }
    }
  }
  return out
}

export function formatReadableValue(
  value: unknown,
  field?: FieldDef,
  lookups: ValueLookups = {},
): string {
  if (value === null || value === undefined || value === '') return '—'

  if (Array.isArray(value)) {
    if (!value.length) return '—'
    // 子表：数组元素是行对象，展示行数即可
    if (value.some((item) => typeof item === 'object' && item !== null)) {
      return `${value.length} 行`
    }
  }

  if (!field) return formatUnknownValue(value)

  if (field.type === 'attachment' || field.type === 'image') {
    const ids = Array.isArray(value) ? value : [value]
    return ids
      .map((id) => lookups.attachmentName?.(Number(id)) || `附件 #${id}`)
      .join('、')
  }

  if (field.type === 'cascader') {
    // 级联值只有 option value，当前父值在 diff 里拿不到；按全部候选找唯一标签
    const options = Object.values(field.cascader?.options_by_parent ?? {}).flat()
    const hit = options.find((option) => String(option.value) === String(value))
    return hit?.label ?? formatUnknownValue(value)
  }

  if (field.type === 'subtable') {
    return Array.isArray(value) ? `${value.length} 行` : formatUnknownValue(value)
  }

  return formatValue(field, value, (kind, id) => {
    const numeric = Number(id)
    const name = kind === 'dept'
      ? lookups.deptName?.(numeric)
      : lookups.userName?.(numeric)
    // 空字符串也当作没查到：宁可回退成 #id，也不要显示成空白让人以为值丢了
    return name || `#${id}`
  })
}

function formatUnknownValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => formatUnknownValue(item)).join('、') : '—'
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object' && value !== null) return JSON.stringify(value)
  return String(value)
}
