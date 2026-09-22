/**
 * 前端公式求值。
 *
 * **权威实现在后端**（`backend/app/engine/expressions.py`）。这里只做输入时的
 * 即时显示 —— 提交时服务端会重算并覆盖（决策 D4），所以：
 *   - 算不出来一律返回 null，绝不抛错打断用户输入
 *   - 语义必须与后端一致，靠 `docs/formula-test-vectors.json` 共享测试向量保证
 *
 * 与后端的两处实现差异（不可避免）：
 *   - 后端用 Decimal，这里用 IEEE754 double；所有结果统一按 6 位小数归一，
 *     抵消 0.1+0.2=0.30000000000000004 这类浮点噪声
 *   - ROUND 后端用 ROUND_HALF_UP，这里用 Math.round 绝对值实现同样的语义
 *     （JS 的 Math.round(-2.5) 得 -2，不是我们要的 -3）
 */

import type { FieldDef, FieldFormula, FormSchema, SectionDef } from '@/types/form'

/** 公式里允许调用的函数白名单，必须与后端 core/constants.FORMULA_FUNCTIONS 一致。 */
export const FORMULA_FUNCTIONS = new Set(['ROUND', 'ABS', 'MIN', 'MAX'])

export class FormulaError extends Error {}

type Mode = 'numeric' | 'string'

/** 结果保留的位数，与后端的 _clean 一致 */
const RESULT_PRECISION = 6

// --------------------------------------------------------------------------- 词法

type Token =
  | { kind: 'number'; value: number; pos: number }
  | { kind: 'string'; value: string; pos: number }
  | { kind: 'ident'; value: string; pos: number }
  | { kind: 'op'; value: string; pos: number }

const TOKEN_RE = /(\d+\.\d+|\d+\.|\.\d+|\d+)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|([A-Za-z_][A-Za-z0-9_]*)|([+\-*/%(),])/y

const ESCAPES: Record<string, string> = { n: '\n', t: '\t', r: '\r', '\\': '\\', '"': '"', "'": "'" }

function unescape(raw: string): string {
  const body = raw.slice(1, -1)
  let out = ''
  for (let i = 0; i < body.length; i += 1) {
    const ch = body[i]
    if (ch === '\\' && i + 1 < body.length) {
      const next = body[i + 1]
      out += ESCAPES[next] ?? next
      i += 1
    } else {
      out += ch
    }
  }
  return out
}

function tokenize(expression: string): Token[] {
  const tokens: Token[] = []
  let pos = 0
  while (pos < expression.length) {
    // 跳过空白
    const skipped = /^\s+/.exec(expression.slice(pos))
    if (skipped) {
      pos += skipped[0].length
      if (pos >= expression.length) break
    }
    TOKEN_RE.lastIndex = pos
    const match = TOKEN_RE.exec(expression)
    if (!match || match.index !== pos) {
      throw new FormulaError(`公式在第 ${pos} 个字符处无法解析`)
    }
    pos = TOKEN_RE.lastIndex
    const [raw, num, str, ident, op] = match
    if (num !== undefined) tokens.push({ kind: 'number', value: Number(num), pos: match.index })
    else if (str !== undefined) tokens.push({ kind: 'string', value: unescape(raw), pos: match.index })
    else if (ident !== undefined) tokens.push({ kind: 'ident', value: ident, pos: match.index })
    else tokens.push({ kind: 'op', value: op, pos: match.index })
  }
  return tokens
}

// --------------------------------------------------------------------------- 数值工具

/** 归一到位数精度，抵消浮点噪声（0.1+0.2 → 0.3） */
function normalize(value: number): number {
  if (!Number.isFinite(value)) return value
  const rounded = Number(value.toFixed(RESULT_PRECISION))
  return Object.is(rounded, -0) ? 0 : rounded
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  if (typeof value === 'boolean') return value ? 1 : 0
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return null
    // 用 Number 而不是 parseFloat：parseFloat("3abc") 会得 3，那是错的
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return ''
  if (typeof value === 'number') return String(normalize(value))
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value)
}

/** 四舍五入（不是 JS Math.round 那样对负数朝 +∞ 取整） */
function roundHalfUp(value: number, digits: number): number {
  const factor = 10 ** digits
  const scaled = Math.abs(value) * factor
  // +1e-9 抵消 1.005*100=100.49999999999999 这类表示误差
  const rounded = Math.round(scaled + 1e-9) / factor
  return normalize(value < 0 ? -rounded : rounded)
}

// --------------------------------------------------------------------------- 语法分析

interface ParserOptions {
  mode: Mode
  knownKeys?: Set<string> | null
}

class Parser {
  private pos = 0

  constructor(
    private readonly tokens: Token[],
    private readonly values: Record<string, unknown>,
    private readonly options: ParserOptions,
  ) {}

  private peek(): Token | null {
    return this.tokens[this.pos] ?? null
  }

  private next(): Token {
    const token = this.peek()
    if (!token) throw new FormulaError('公式意外结束')
    this.pos += 1
    return token
  }

  private acceptOp(...ops: string[]): string | null {
    const token = this.peek()
    if (token && token.kind === 'op' && ops.includes(token.value)) {
      this.pos += 1
      return token.value
    }
    return null
  }

  parse(): unknown {
    const value = this.expr()
    if (this.pos !== this.tokens.length) {
      throw new FormulaError(`公式在第 ${this.tokens[this.pos].pos} 个字符处有多余内容`)
    }
    return value
  }

  private expr(): unknown {
    let left = this.term()
    let op = this.acceptOp('+', '-')
    while (op !== null) {
      const right = this.term()
      left = this.additive(op, left, right)
      op = this.acceptOp('+', '-')
    }
    return left
  }

  private term(): unknown {
    let left = this.unary()
    let op = this.acceptOp('*', '/', '%')
    while (op !== null) {
      if (this.options.mode === 'string') {
        throw new FormulaError('文本拼接公式里不能使用 * / % 运算')
      }
      const right = this.unary()
      left = this.multiplicative(op, left, right)
      op = this.acceptOp('*', '/', '%')
    }
    return left
  }

  private unary(): unknown {
    const op = this.acceptOp('-', '+')
    if (op !== null) {
      if (this.options.mode === 'string') {
        throw new FormulaError('文本拼接公式里不能使用正负号')
      }
      const operand = this.unary()
      const num = toNumber(operand)
      if (num === null) throw new FormulaError('不能对非数字取负')
      return normalize(op === '-' ? -num : num)
    }
    return this.primary()
  }

  private primary(): unknown {
    const token = this.next()

    if (token.kind === 'number') return normalize(token.value)

    if (token.kind === 'string') {
      if (this.options.mode !== 'string') {
        throw new FormulaError('数字公式里不能出现文本字面量（如需拼接请把公式类型改为「文本拼接」）')
      }
      return token.value
    }

    if (token.kind === 'ident') {
      const name = token.value
      if (this.acceptOp('(') !== null) {
        if (this.options.mode === 'string') {
          throw new FormulaError('文本拼接公式里不能调用函数')
        }
        return this.call(name)
      }
      const known = this.options.knownKeys
      if (known && !known.has(name)) {
        throw new FormulaError(`公式引用了不存在的字段：${name}`)
      }
      // 字段已声明但当前没值 → undefined，由运算符按 0 / 空串处理
      return this.values[name]
    }

    if (token.kind === 'op' && token.value === '(') {
      const value = this.expr()
      if (this.acceptOp(')') === null) throw new FormulaError('公式缺少右括号')
      return value
    }

    throw new FormulaError(`公式在第 ${token.pos} 个字符处出现意外符号`)
  }

  private call(name: string): unknown {
    if (!FORMULA_FUNCTIONS.has(name)) {
      throw new FormulaError(`不支持的函数：${name}`)
    }

    const args: unknown[] = []
    if (this.acceptOp(')') === null) {
      args.push(this.expr())
      while (this.acceptOp(',') !== null) args.push(this.expr())
      if (this.acceptOp(')') === null) throw new FormulaError(`${name}() 缺少右括号`)
    }

    const nums: number[] = []
    for (const arg of args) {
      const num = toNumber(arg)
      if (num === null) throw new FormulaError(`${name}() 的参数必须是数字`)
      nums.push(num)
    }

    switch (name) {
      case 'ROUND':
        if (nums.length !== 2) throw new FormulaError('ROUND() 需要 2 个参数：ROUND(值, 小数位)')
        return roundHalfUp(nums[0], Math.trunc(nums[1]))
      case 'ABS':
        if (nums.length !== 1) throw new FormulaError('ABS() 需要 1 个参数')
        return normalize(Math.abs(nums[0]))
      case 'MIN':
        if (!nums.length) throw new FormulaError('MIN() 至少需要 1 个参数')
        return normalize(Math.min(...nums))
      case 'MAX':
        if (!nums.length) throw new FormulaError('MAX() 至少需要 1 个参数')
        return normalize(Math.max(...nums))
      default:
        throw new FormulaError(`不支持的函数：${name}`)
    }
  }

  private additive(op: string, left: unknown, right: unknown): unknown {
    if (this.options.mode === 'string') {
      if (op === '-') throw new FormulaError('文本拼接公式里不能使用减号')
      return stringify(left) + stringify(right)
    }
    // 数值模式：缺失值按 0，不做字符串拼接
    const a = toNumber(left) ?? 0
    const b = toNumber(right) ?? 0
    return normalize(op === '+' ? a + b : a - b)
  }

  private multiplicative(op: string, left: unknown, right: unknown): unknown {
    const a = toNumber(left) ?? 0
    const b = toNumber(right) ?? 0
    if (op === '*') return normalize(a * b)
    if (b === 0) return null // 除零返回 null，不打断输入
    if (op === '/') return normalize(a / b)
    return normalize(a % b)
  }
}

// --------------------------------------------------------------------------- 日期

function toDate(value: unknown): Date | null {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value !== 'string' || !value.trim()) return null
  const text = value.trim().replace(/\//g, '-')
  // 纯日期按本地零点解析，避免 new Date('2026-09-01') 被当成 UTC 导致差一天
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text)
  if (dateOnly) {
    const [, y, m, d] = dateOnly
    return new Date(Number(y), Number(m) - 1, Number(d))
  }
  const parsed = new Date(text)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function daysBetween(start: Date, end: Date): number {
  const msPerDay = 24 * 60 * 60 * 1000
  const s = Date.UTC(start.getFullYear(), start.getMonth(), start.getDate())
  const e = Date.UTC(end.getFullYear(), end.getMonth(), end.getDate())
  return Math.round((e - s) / msPerDay)
}

// --------------------------------------------------------------------------- 入口

export function evaluateArithmetic(
  expression: string,
  values: Record<string, unknown>,
  knownKeys?: Set<string> | null,
): unknown {
  if (!expression?.trim()) return null
  return new Parser(tokenize(expression), values, { mode: 'numeric', knownKeys }).parse()
}

export function evaluateConcat(
  expression: string,
  values: Record<string, unknown>,
  knownKeys?: Set<string> | null,
): unknown {
  if (!expression?.trim()) return null
  return new Parser(tokenize(expression), values, { mode: 'string', knownKeys }).parse()
}

export interface EvaluateOptions {
  subtableRows?: Record<string, Array<Record<string, unknown>>>
  knownKeys?: Set<string> | null
}

/** 按公式类型求值。任何失败返回 null（表单不该因公式算不出来而崩）。 */
export function evaluateFormula(
  formula: FieldFormula,
  values: Record<string, unknown>,
  options: EvaluateOptions = {},
): unknown {
  try {
    if (formula.type === 'arithmetic') {
      return evaluateArithmetic(formula.expression ?? '', values, options.knownKeys)
    }
    if (formula.type === 'concat') {
      return evaluateConcat(formula.expression ?? '', values, options.knownKeys)
    }
    if (formula.type === 'subtable_sum') {
      const rows = options.subtableRows?.[formula.subtable_key ?? ''] ?? []
      return normalize(
        rows.reduce((sum, row) => sum + (toNumber(row[formula.column_key ?? '']) ?? 0), 0),
      )
    }
    if (formula.type === 'date_diff') {
      const start = toDate(values[formula.start_field ?? ''])
      const end = toDate(values[formula.end_field ?? ''])
      if (!start || !end) return null
      return daysBetween(start, end)
    }
  } catch {
    return null
  }
  return null
}

function collectSubtableRows(
  schema: FormSchema,
  values: Record<string, unknown>,
): Record<string, Array<Record<string, unknown>>> {
  const rows: Record<string, Array<Record<string, unknown>>> = {}
  for (const section of schema.sections) {
    for (const field of section.fields) {
      if (field.type !== 'subtable') continue
      const raw = values[field.key]
      if (Array.isArray(raw)) {
        rows[field.key] = raw.filter(
          (r): r is Record<string, unknown> => typeof r === 'object' && r !== null,
        )
      }
    }
  }
  return rows
}

/**
 * 重算 schema 里所有公式字段，返回需要覆盖的 `{key: 新值}`。
 *
 * 与后端同构的两趟执行：先算子表行内公式并回填，再算顶层公式 ——
 * 否则「子表合计」会取到还没算出来的行内小计。
 * （输入框失焦时调用；提交时后端会再算一遍并覆盖。）
 */
export function evaluateSchemaFormulas(
  schema: FormSchema,
  values: Record<string, unknown>,
): Record<string, unknown> {
  const updates: Record<string, unknown> = {}
  const subtableRows = collectSubtableRows(schema, values)

  const subtables: FieldDef[] = []
  const topLevel: FieldDef[] = []
  const topKnown = new Set<string>()

  for (const section of schema.sections) {
    for (const field of section.fields) {
      topKnown.add(field.key)
      if (field.type === 'subtable') subtables.push(field)
      else if (field.formula) topLevel.push(field)
    }
  }

  for (const subtable of subtables) {
    const formulaCols = (subtable.columns ?? []).filter((c) => c.formula)
    const rows = subtableRows[subtable.key]
    if (!formulaCols.length || !rows) continue

    const columnKeys = new Set((subtable.columns ?? []).map((c) => c.key))
    const newRows = rows.map((row) => {
      const computed = { ...row }
      for (const col of formulaCols) {
        computed[col.key] = evaluateFormula(col.formula!, computed, {
          subtableRows,
          knownKeys: columnKeys,
        })
      }
      return computed
    })
    subtableRows[subtable.key] = newRows
    updates[subtable.key] = newRows
  }

  for (const field of topLevel) {
    updates[field.key] = evaluateFormula(field.formula!, values, {
      subtableRows,
      knownKeys: topKnown,
    })
  }

  return updates
}

/** 从 schema 里取出全部字段（含子表列），供设计器与校验器遍历。 */
export function flattenFields(schema: FormSchema): Array<{ field: FieldDef; section: SectionDef }> {
  const out: Array<{ field: FieldDef; section: SectionDef }> = []
  for (const section of schema.sections) {
    for (const field of section.fields) {
      out.push({ field, section })
      for (const col of field.columns ?? []) {
        out.push({ field: col, section })
      }
    }
  }
  return out
}
