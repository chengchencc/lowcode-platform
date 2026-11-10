/**
 * 条件表达式类型（流程分支与表单联动规则共用）。
 *
 * 与后端 `app/schemas/conditions.py` 对齐。流程类型与表单规则都从这里引用，
 * 避免表单规则反向依赖流程定义。
 */

export type Comparison =
  | '=='
  | '!='
  | '>'
  | '>='
  | '<'
  | '<='
  | 'in'
  | 'not_in'
  | 'contains'
  | 'is_empty'
  | 'is_not_empty'

export interface Condition {
  field: string
  cmp: Comparison
  value?: unknown
}

export interface ConditionGroup {
  op: 'and' | 'or'
  conditions: Array<Condition | ConditionGroup>
}

/** 判断是否是嵌套组（有 op/conditions 字段）还是叶子条件（有 field） */
export function isConditionGroup(item: Condition | ConditionGroup): item is ConditionGroup {
  return 'conditions' in item
}
