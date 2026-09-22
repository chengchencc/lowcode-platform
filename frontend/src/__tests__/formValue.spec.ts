/**
 * 字段值校验与级联下拉的客户端行为。
 *
 * 这是**提示层**：真正的边界在服务端 `app/engine/value_rules.py`。
 * 两边规则必须一致 —— 那边有对应的 `tests/test_value_rules.py`。
 */

import { describe, expect, it } from 'vitest'

import type { FieldDef, FormSchema } from '@/types/form'
import { clearStaleCascades, validateValues } from '@/utils/formValue'

const ALL_VISIBLE: Record<string, { visible: boolean; editable: boolean; required: boolean }> = {}

function schema(fields: FieldDef[], stage = 'apply'): FormSchema {
  return {
    sections: [{ key: 's1', title: '申请', stage: stage as 'apply', fields }],
  }
}

function statesFor(form: FormSchema) {
  const states: Record<string, { visible: boolean; editable: boolean; required: boolean }> = {
    ...ALL_VISIBLE,
  }
  for (const section of form.sections) {
    for (const field of section.fields) {
      states[field.key] = { visible: true, editable: true, required: field.required ?? false }
    }
  }
  return states
}

const CASCADER_SCHEMA = schema([
  {
    key: 'category',
    label: '费用类别',
    type: 'select',
    options: [
      { label: '差旅', value: 'travel' },
      { label: '办公', value: 'office' },
    ],
  },
  {
    key: 'sub',
    label: '费用明细',
    type: 'cascader',
    cascader: {
      parent_field: 'category',
      options_by_parent: {
        travel: [
          { label: '机票', value: 'flight' },
          { label: '住宿', value: 'hotel' },
        ],
        office: [{ label: '打印', value: 'print' }],
      },
    },
  },
])

describe('选项与级联校验', () => {
  it('取值不在选项里要报出来', () => {
    const form = schema([
      {
        key: 'type',
        label: '费用类型',
        type: 'select',
        options: [{ label: '差旅', value: 'travel' }],
      },
    ])
    const issues = validateValues(form, { type: 'other' }, statesFor(form))
    expect(issues.map((i) => i.message)).toEqual(['费用类型的取值不在选项里'])
  })

  it('复选逐个检查', () => {
    const form = schema([
      {
        key: 'tags',
        label: '标签',
        type: 'checkbox',
        options: [{ label: 'A', value: 'a' }],
      },
    ])
    expect(validateValues(form, { tags: ['a'] }, statesFor(form))).toEqual([])
    expect(validateValues(form, { tags: ['a', 'z'] }, statesFor(form))).toHaveLength(1)
  })

  it('没配选项的控件不做限制（先建字段后补选项是允许的）', () => {
    const form = schema([{ key: 'type', label: '类型', type: 'select' }])
    expect(validateValues(form, { type: '任意' }, statesFor(form))).toEqual([])
  })

  it('级联值必须与父字段的当前值匹配', () => {
    const states = statesFor(CASCADER_SCHEMA)
    expect(validateValues(CASCADER_SCHEMA, { category: 'travel', sub: 'flight' }, states)).toEqual([])

    const issues = validateValues(CASCADER_SCHEMA, { category: 'office', sub: 'flight' }, states)
    expect(issues.map((i) => i.message)).toEqual(['费用明细与上级选项不匹配'])
    expect(issues[0].key).toBe('sub')
  })

  it('父字段没选时提示先选上级', () => {
    const states = statesFor(CASCADER_SCHEMA)
    const issues = validateValues(CASCADER_SCHEMA, { sub: 'flight' }, states)
    expect(issues.map((i) => i.message)).toEqual(['请先选择费用明细的上级选项'])
  })
})

describe('父字段变化时清掉过期的级联值', () => {
  it('换类别后子值对不上就清空', () => {
    const next = clearStaleCascades(
      CASCADER_SCHEMA,
      { category: 'office', sub: 'flight' },
      'category',
    )
    expect(next.sub).toBeNull()
    expect(next.category).toBe('office')
  })

  it('子值在新父选项下仍然合法就不动它', () => {
    const values = { category: 'travel', sub: 'hotel' }
    const next = clearStaleCascades(CASCADER_SCHEMA, values, 'category')
    expect(next).toBe(values) // 没有变化时返回原对象，避免无谓重渲染
  })

  it('改的是别的字段时不受影响', () => {
    const values = { category: 'travel', sub: 'flight' }
    expect(clearStaleCascades(CASCADER_SCHEMA, values, 'unrelated')).toBe(values)
  })

  it('父字段被清空时子值也清掉', () => {
    const next = clearStaleCascades(CASCADER_SCHEMA, { category: null, sub: 'flight' }, 'category')
    expect(next.sub).toBeNull()
  })

  it('子表行内级联只看同一行的父列', () => {
    const form = schema([
      {
        key: 'items',
        label: '明细',
        type: 'subtable',
        columns: [
          {
            key: 'category',
            label: '类别',
            type: 'select',
            options: [
              { label: '差旅', value: 'travel' },
              { label: '办公', value: 'office' },
            ],
          },
          {
            key: 'sub',
            label: '细项',
            type: 'cascader',
            cascader: {
              parent_field: 'category',
              options_by_parent: {
                travel: [{ label: '机票', value: 'flight' }],
                office: [{ label: '打印', value: 'print' }],
              },
            },
          },
        ],
      },
    ])

    const next = clearStaleCascades(
      form,
      { items: [{ category: 'office', sub: 'flight' }, { category: 'travel', sub: 'flight' }] },
      'category',
    ) as { items: Array<Record<string, unknown>> }

    expect(next.items[0].sub).toBeNull() // 第 1 行对不上 → 清掉
    expect(next.items[1].sub).toBe('flight') // 第 2 行没问题 → 保留
    expect(next.items[1].category).toBe('travel')
  })
})
