/**
 * 前端公式求值测试。
 *
 * **用例来自 `docs/formula-test-vectors.json`** —— 与后端
 * `backend/tests/test_engine_expressions.py` 跑的是同一份文件（决策 D4）。
 * 任何一侧语义漂移，这里或那边就会红。
 */

import { describe, expect, it } from 'vitest'

import vectors from '../../../docs/formula-test-vectors.json'
import type { FormSchema } from '@/types/form'
import type { FieldFormula } from '@/types/form'
import {
  evaluateArithmetic,
  evaluateFormula,
  evaluateSchemaFormulas,
  FormulaError,
} from '@/utils/formula'

interface Vector {
  name: string
  formula: FieldFormula
  values: Record<string, unknown>
  subtable_rows?: Record<string, Array<Record<string, unknown>>>
  known_keys?: string[]
  expected: unknown
}

interface ErrorVector {
  name: string
  formula: FieldFormula
  values: Record<string, unknown>
  known_keys?: string[]
  expect_error: boolean
}

const VECTORS = vectors.vectors as Vector[]
const ERROR_VECTORS = vectors.error_vectors as ErrorVector[]

describe('公式求值（与后端共享测试向量）', () => {
  for (const c of VECTORS) {
    it(c.name, () => {
      const got = evaluateFormula(c.formula, c.values, {
        subtableRows: c.subtable_rows,
        knownKeys: c.known_keys ? new Set(c.known_keys) : null,
      })
      expect(got).toEqual(c.expected)
    })
  }

  for (const c of ERROR_VECTORS) {
    it(c.name, () => {
      expect(() =>
        evaluateArithmetic(c.formula.expression ?? '', c.values, c.known_keys ? new Set(c.known_keys) : null),
      ).toThrow(FormulaError)
    })
  }
})

describe('数值精度', () => {
  it('浮点噪声被归一（0.1 + 0.2 应得 0.3 而不是 0.30000000000000004）', () => {
    expect(evaluateArithmetic('a + b', { a: 0.1, b: 0.2 })).toBe(0.3)
  })

  it('ROUND 对负数也按四舍五入（不是 Math.round 的朝 +∞ 取整）', () => {
    expect(evaluateArithmetic('ROUND(a, 0)', { a: -2.5 })).toBe(-3)
    expect(evaluateArithmetic('ROUND(a, 0)', { a: 2.5 })).toBe(3)
  })

  it('不把 "3abc" 当成数字 3（Number 而非 parseFloat）', () => {
    expect(evaluateArithmetic('a + 1', { a: '3abc' })).toBe(1)
  })
})

describe('日期差按自然日计算', () => {
  it('纯日期按本地零点解析，不受时区影响', () => {
    expect(evaluateFormula(
      { type: 'date_diff', start_field: 's', end_field: 'e' },
      { s: '2026-09-01', e: '2026-09-04' },
    )).toBe(3)
  })

  it('跨夏令时的日期区间也是自然日差', () => {
    // 3 月到 11 月跨越了北半球夏令时切换
    expect(evaluateFormula(
      { type: 'date_diff', start_field: 's', end_field: 'e' },
      { s: '2026-03-01', e: '2026-11-01' },
    )).toBe(245)
  })
})

describe('schema 整体重算与后端同构', () => {
  const schema: FormSchema = {
    sections: [
      {
        key: 'sec',
        title: '申请',
        stage: 'apply',
        fields: [
          { key: 'qty', label: '数量', type: 'number' },
          { key: 'price', label: '单价', type: 'number' },
          {
            key: 'items',
            label: '明细',
            type: 'subtable',
            columns: [
              { key: 'qty', label: '数量', type: 'number' },
              { key: 'price', label: '单价', type: 'number' },
              {
                key: 'subtotal',
                label: '小计',
                type: 'formula',
                formula: { type: 'arithmetic', expression: 'qty * price' },
              },
            ],
          },
          {
            key: 'total',
            label: '合计',
            type: 'formula',
            formula: { type: 'subtable_sum', subtable_key: 'items', column_key: 'subtotal' },
          },
        ],
      },
    ],
  }

  it('子表行内公式逐行算，顶层合计汇总的是算好的行', () => {
    const updates = evaluateSchemaFormulas(schema, {
      qty: 2,
      price: 10,
      items: [
        { qty: 3, price: 12.5 },
        { qty: 1, price: 100 },
      ],
    })

    expect(updates.items).toEqual([
      { qty: 3, price: 12.5, subtotal: 37.5 },
      { qty: 1, price: 100, subtotal: 100 },
    ])
    expect(updates.total).toBe(137.5)
  })

  it('子表为空时合计为 0', () => {
    const updates = evaluateSchemaFormulas(schema, { items: [] })
    expect(updates.total).toBe(0)
  })

  it('不依赖字段书写顺序（两趟执行）', () => {
    // 把 total 放到 items 前面，结果应当一致
    const reordered: FormSchema = {
      sections: [
        {
          key: 'sec',
          title: '申请',
          fields: [
            schema.sections[0].fields[3], // total
            schema.sections[0].fields[2], // items
          ],
        },
      ],
    }
    const updates = evaluateSchemaFormulas(reordered, {
      items: [{ qty: 2, price: 5 }],
    })
    expect(updates.total).toBe(10)
  })
})
