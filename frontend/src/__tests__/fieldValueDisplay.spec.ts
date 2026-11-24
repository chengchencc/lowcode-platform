/**
 * 处理历史 / 快照对照里的字段值展示。
 *
 * 表单里存的是 option value、人员/部门 id、附件 id —— 直接 String()
 * 出来用户读不懂。这里锁住「按 schema 换成人话、查不到时退回原值」的行为。
 */

import { describe, expect, it } from 'vitest'

import type { FieldDef, FormSchema } from '@/types/form'
import { buildFieldIndex, formatReadableValue } from '@/utils/fieldValueDisplay'

function schema(fields: FieldDef[]): FormSchema {
  return { sections: [{ key: 's1', title: '申请', fields }] }
}

const field = (patch: Partial<FieldDef> & Pick<FieldDef, 'key' | 'type'>): FieldDef => ({
  label: patch.key,
  ...patch,
})

describe('buildFieldIndex', () => {
  it('收录顶层字段与子表列（a[].b / a.b 两种引用）', () => {
    const index = buildFieldIndex(
      schema([
        field({ key: 'reason', type: 'textarea' }),
        field({
          key: 'items',
          type: 'subtable',
          columns: [field({ key: 'amount', type: 'number' })],
        }),
      ]),
    )

    expect(index.get('reason')?.type).toBe('textarea')
    expect(index.get('items[].amount')?.type).toBe('number')
    expect(index.get('items.amount')?.type).toBe('number')
  })

  it('没有 schema 时返回空索引', () => {
    expect(buildFieldIndex(null).size).toBe(0)
    expect(buildFieldIndex(undefined).size).toBe(0)
  })
})

describe('formatReadableValue', () => {
  it('空值统一显示破折号', () => {
    expect(formatReadableValue(null)).toBe('—')
    expect(formatReadableValue(undefined)).toBe('—')
    expect(formatReadableValue('')).toBe('—')
    expect(formatReadableValue([], field({ key: 'tags', type: 'checkbox' }))).toBe('—')
  })

  it('选择框把 option value 换成选项标签（含多选）', () => {
    const type = field({
      key: 'type',
      type: 'select',
      options: [
        { label: '差旅', value: 'travel' },
        { label: '办公', value: 'office' },
      ],
    })
    expect(formatReadableValue('travel', type)).toBe('差旅')
    expect(formatReadableValue(['travel', 'office'], type)).toBe('差旅、办公')
  })

  it('附件 id 换成文件名，查不到的保留 id 兜底', () => {
    const files = field({ key: 'invoice', type: 'attachment' })
    const names = new Map([
      [11, '发票.pdf'],
      [12, '行程单.png'],
    ])
    const lookup = { attachmentName: (id: number) => names.get(id) }

    expect(formatReadableValue([11, 12], files, lookup)).toBe('发票.pdf、行程单.png')
    expect(formatReadableValue([11, 99], files, lookup)).toBe('发票.pdf、附件 #99')
  })

  it('人员 / 部门 id 换成名字，查不到时保留 id', () => {
    const lookup = {
      userName: (id: number) => (id === 1 ? '张三' : ''),
      deptName: (id: number) => (id === 20 ? '财务部' : ''),
    }
    expect(
      formatReadableValue(1, field({ key: 'owner', type: 'user' }), lookup),
    ).toBe('张三')
    expect(
      formatReadableValue([1, 2], field({ key: 'owners', type: 'user_multi' }), lookup),
    ).toBe('张三、#2')
    expect(
      formatReadableValue(20, field({ key: 'dept', type: 'dept' }), lookup),
    ).toBe('财务部')
  })

  it('级联值从全部候选里找标签', () => {
    const city = field({
      key: 'city',
      type: 'cascader',
      cascader: {
        parent_field: 'province',
        options_by_parent: {
          zj: [
            { label: '杭州', value: 'hz' },
            { label: '宁波', value: 'nb' },
          ],
          js: [{ label: '南京', value: 'nj' }],
        },
      },
    })
    expect(formatReadableValue('nj', city)).toBe('南京')
    expect(formatReadableValue('unknown', city)).toBe('unknown')
  })

  it('子表只展示行数', () => {
    const items = field({ key: 'items', type: 'subtable' })
    expect(formatReadableValue([{ amount: 1 }, { amount: 2 }], items)).toBe('2 行')
  })

  it('schema 里找不到的字段退回原始值', () => {
    expect(formatReadableValue(true)).toBe('是')
    expect(formatReadableValue(false)).toBe('否')
    expect(formatReadableValue(42)).toBe('42')
    expect(formatReadableValue('old_value')).toBe('old_value')
    expect(formatReadableValue([1, 2])).toBe('1、2')
  })
})
