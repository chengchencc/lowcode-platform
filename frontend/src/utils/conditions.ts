/**
 * 条件表达式求值（与后端 `app/engine/conditions.py` 同构）。
 *
 * 流程分支由服务端求值；表单联动规则需要在输入时即时反馈，所以前端也需要
 * 同一套语义。缺失字段一律视为「不匹配」，不抛错 —— 表单还没填完是常态。
 */

import type { Condition, ConditionGroup } from '@/types/conditions'
import { isConditionGroup } from '@/types/conditions'

const MISSING = Symbol('missing')

function getField(values: Record<string, unknown>, field: string): unknown | typeof MISSING {
  if (field.includes('[].')) {
    const [tableKey, columnKey] = field.split('[].', 2)
    const rows = values[tableKey]
    if (Array.isArray(rows) && rows.length && typeof rows[0] === 'object' && rows[0] !== null) {
      return (rows[0] as Record<string, unknown>)[columnKey] ?? MISSING
    }
    return MISSING
  }
  return Object.prototype.hasOwnProperty.call(values, field) ? values[field] : MISSING
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === MISSING || value === '') return null
  if (typeof value === 'boolean') return value ? 1 : 0
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') {
    const num = Number(value.trim())
    return Number.isFinite(num) ? num : null
  }
  return null
}

function isEmpty(value: unknown): boolean {
  if (value === MISSING || value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value as object).length === 0
  return false
}

function equals(left: unknown, right: unknown): boolean {
  if (left === MISSING) return false
  if (typeof left === 'boolean' || typeof right === 'boolean') {
    return Boolean(left) === Boolean(right)
  }
  const ln = toNumber(left)
  const rn = toNumber(right)
  if (ln !== null && rn !== null) return ln === rn
  if (Array.isArray(left) || Array.isArray(right)) {
    const ll = Array.isArray(left) ? left : [left]
    const rl = Array.isArray(right) ? right : [right]
    return ll.length === rl.length && ll.every((item, index) => equals(item, rl[index]))
  }
  return String(left) === String(right)
}

function compare(left: unknown, cmp: Condition['cmp'], right: unknown): boolean {
  if (cmp === 'is_empty') return isEmpty(left)
  if (cmp === 'is_not_empty') return !isEmpty(left)
  if (left === MISSING || left === null || left === undefined) return false

  if (cmp === 'in') {
    return Array.isArray(right) && right.some((item) => equals(left, item))
  }
  if (cmp === 'not_in') {
    return !Array.isArray(right) || !right.some((item) => equals(left, item))
  }
  if (cmp === 'contains') {
    if (Array.isArray(left)) return left.some((item) => equals(item, right))
    return typeof left === 'string' && typeof right === 'string' && left.includes(right)
  }
  if (cmp === '==') return equals(left, right)
  if (cmp === '!=') return !equals(left, right)

  const ln = toNumber(left)
  const rn = toNumber(right)
  if (ln !== null && rn !== null) {
    if (cmp === '>') return ln > rn
    if (cmp === '>=') return ln >= rn
    if (cmp === '<') return ln < rn
    return ln <= rn
  }
  const ls = String(left)
  const rs = String(right)
  if (cmp === '>') return ls > rs
  if (cmp === '>=') return ls >= rs
  if (cmp === '<') return ls < rs
  return ls <= rs
}

export function evaluateCondition(condition: Condition, values: Record<string, unknown>): boolean {
  return compare(getField(values, condition.field), condition.cmp, condition.value)
}

export function evaluateGroup(group: ConditionGroup, values: Record<string, unknown>): boolean {
  const results = group.conditions.map((item) =>
    isConditionGroup(item) ? evaluateGroup(item, values) : evaluateCondition(item, values),
  )
  if (!results.length) return group.op === 'and'
  return group.op === 'and' ? results.every(Boolean) : results.some(Boolean)
}
