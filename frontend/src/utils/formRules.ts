/**
 * 表单字段联动规则的前端求值（M9）。
 *
 * 与后端 `app/engine/form_rules.py` 同一套语义：规则只收紧权限，
 * `hidden > readonly > required`，节点权限已经隐藏的字段不会被规则点亮。
 */

import type { FieldState, FormRule } from '@/types/form'
import { evaluateGroup } from '@/utils/conditions'

function restrict(state: FieldState, effect: 'hidden' | 'readonly' | 'required'): FieldState {
  if (effect === 'hidden') return { visible: false, editable: false, required: false }
  if (effect === 'readonly') {
    if (!state.visible) return state
    return { visible: true, editable: false, required: false }
  }
  // required 只在可见且可编辑时有意义
  if (!state.visible || !state.editable) return state
  return { ...state, required: true }
}

export function applyFormRules(
  base: Record<string, FieldState>,
  rules: FormRule[] | null | undefined,
  values: Record<string, unknown>,
): Record<string, FieldState> {
  if (!rules?.length) return base

  const out: Record<string, FieldState> = { ...base }
  for (const rule of rules) {
    if (!evaluateGroup(rule.when, values)) continue
    for (const effect of rule.effects) {
      const current = out[effect.target]
      if (!current) continue
      out[effect.target] = restrict(current, effect.effect)
    }
  }
  return out
}

/** 命中「隐藏时清值」的字段（只清基础权限本来可见的）。 */
export function clearHiddenKeys(
  base: Record<string, FieldState>,
  rules: FormRule[] | null | undefined,
  values: Record<string, unknown>,
): string[] {
  if (!rules?.length) return []
  const out: string[] = []
  for (const rule of rules) {
    if (!rule.clear_when_hidden || !evaluateGroup(rule.when, values)) continue
    for (const effect of rule.effects) {
      if (effect.effect !== 'hidden') continue
      if (base[effect.target]?.visible && !out.includes(effect.target)) {
        out.push(effect.target)
      }
    }
  }
  return out
}

/** 返回清掉隐藏字段后的新值（无变化时返回原对象）。 */
export function clearHiddenValues(
  base: Record<string, FieldState>,
  rules: FormRule[] | null | undefined,
  values: Record<string, unknown>,
): Record<string, unknown> {
  const keys = clearHiddenKeys(base, rules, values)
  if (!keys.length) return values
  let next = values
  for (const key of keys) {
    if (!(key in next)) continue
    if (next === values) next = { ...values }
    delete next[key]
  }
  return next
}
