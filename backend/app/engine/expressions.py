"""公式求值（PRD §10 #9 基础子集）。

支持四类：
- `arithmetic`   数字四则：`qty * price`、`(a + b) / 2`、`ROUND(x, 2)`
- `subtable_sum` 子表某列合计
- `date_diff`    两个日期相差的天数
- `concat`       文本拼接：`dept + "-" + name`

**刻意不用 `eval()`**：表达式来自设计器配置，属于用户输入。`eval` 会让
「配置一个表单」升级成「在服务端执行任意 Python」。这里手写词法 + 递归下降解析，
可执行的语法被严格限制在四则/拼接 + 白名单函数内。

**运算符语义由公式类型决定，不靠操作数类型猜**：
`arithmetic` 下 `+` 恒为数值加法、缺失字段按 0；`concat` 下 `+` 恒为字符串拼接、
缺失字段按空串。早期版本按「任一侧不是数字就拼接」来推断，导致缺失字段时
`a + b`（b 缺失）返回了字符串 `"5"` 而不是 `5` —— 显式声明类型后这类歧义消失。

**前后端一致性**（决策 D4）：本模块是权威实现，提交时由服务端重算覆盖前端结果。
前端 `src/utils/formula.ts` 只做输入时的即时显示，两边共用
`docs/formula-test-vectors.json` 的测试向量，防止语义漂移。
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from app.core.constants import FORMULA_FUNCTIONS, FormulaType
from app.core.formula_syntax import strip_string_literals  # noqa: F401  供调用方复用
from app.schemas.form_schema import FieldFormula

#: 允许的函数（white-list），定义在 core/constants.py 以便校验器共用
ALLOWED_FUNCTIONS = FORMULA_FUNCTIONS

#: 求值模式。决定 `+` 的含义与缺失值的处理方式。
Mode = Literal["numeric", "string"]

_TOKEN_RE = re.compile(
    r"""
    \s*(?:
        (?P<number>\d+\.\d+|\d+\.|\.\d+|\d+)
      | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<op>[+\-*/%(),])
    )
    """,
    re.VERBOSE,
)

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


class FormulaError(ValueError):
    """公式求值失败（语法错误、引用了不存在的字段等）。"""


# --------------------------------------------------------------------------- 词法


class _Token:
    __slots__ = ("kind", "value", "pos")

    def __init__(self, kind: str, value: Any, pos: int) -> None:
        self.kind = kind
        self.value = value
        self.pos = pos

    def __repr__(self) -> str:  # pragma: no cover - 仅调试用
        return f"<{self.kind}:{self.value!r}>"


def _unescape(raw: str) -> str:
    out: list[str] = []
    i = 0
    body = raw[1:-1]
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _tokenize(expression: str) -> list[_Token]:
    tokens: list[_Token] = []
    pos = 0
    length = len(expression)
    while pos < length:
        match = _TOKEN_RE.match(expression, pos)
        if not match or match.end() == pos:
            raise FormulaError(f"公式在第 {pos} 个字符处无法解析：{expression[pos:pos + 10]!r}")
        pos = match.end()
        if (raw := match.group("number")) is not None:
            tokens.append(_Token("number", Decimal(raw), match.start()))
        elif (literal := match.group("string")) is not None:
            tokens.append(_Token("string", _unescape(literal), match.start()))
        elif (name := match.group("ident")) is not None:
            tokens.append(_Token("ident", name, match.start()))
        else:
            tokens.append(_Token("op", match.group("op"), match.start()))
    return tokens


# --------------------------------------------------------------------------- 数值工具


def _to_decimal(value: Any) -> Decimal | None:
    """把任意输入转成 Decimal；无法转的返回 None（便于公式容错）。"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except (InvalidOperation, AttributeError):
            return None
    return None


def _clean(value: Decimal) -> int | float:
    """Decimal → JSON 友好的数字：整数给 int，否则 float（保留 6 位）。"""
    if value == value.to_integral_value():
        return int(value)
    return float(round(value, 6))


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(_clean(value))
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


# --------------------------------------------------------------------------- 语法分析


class _Parser:
    """递归下降，文法：

        expr    := term (('+' | '-') term)*
        term    := unary (('*' | '/' | '%') unary)*
        unary   := ('-' | '+') unary | primary
        primary := number | string | ident | ident '(' args ')' | '(' expr ')'
    """

    def __init__(
        self,
        tokens: list[_Token],
        values: Mapping[str, Any],
        *,
        mode: Mode,
        known_keys: Collection[str] | None = None,
    ) -> None:
        self._tokens = tokens
        self._pos = 0
        self._values = values
        self._mode = mode
        #: schema 里声明过的字段。给了就是严格模式：引用未声明的字段报错，
        #: 而已声明但当前没值的字段按默认值（0 / 空串）处理。
        #: 不给则一律宽松（任何缺失的标识符都按默认值）。
        self._known_keys = known_keys

    # ---- 游标 ----

    def _peek(self) -> _Token | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _next(self) -> _Token:
        token = self._peek()
        if token is None:
            raise FormulaError("公式意外结束")
        self._pos += 1
        return token

    def _accept_op(self, *ops: str) -> str | None:
        token = self._peek()
        if token is not None and token.kind == "op" and token.value in ops:
            self._pos += 1
            return token.value
        return None

    # ---- 规则 ----

    def parse(self) -> Any:
        value = self._expr()
        if self._pos != len(self._tokens):
            token = self._tokens[self._pos]
            raise FormulaError(f"公式在第 {token.pos} 个字符处有多余内容：{token.value!r}")
        return value

    def _expr(self) -> Any:
        left = self._term()
        while (op := self._accept_op("+", "-")) is not None:
            right = self._term()
            left = self._apply_additive(op, left, right)
        return left

    def _term(self) -> Any:
        left = self._unary()
        while (op := self._accept_op("*", "/", "%")) is not None:
            if self._mode == "string":
                raise FormulaError("文本拼接公式里不能使用 * / % 运算")
            right = self._unary()
            left = self._apply_multiplicative(op, left, right)
        return left

    def _unary(self) -> Any:
        if (op := self._accept_op("-", "+")) is not None:
            if self._mode == "string":
                raise FormulaError("文本拼接公式里不能使用正负号")
            operand = self._unary()
            number = _to_decimal(operand)
            if number is None:
                raise FormulaError(f"不能对非数字取负：{operand!r}")
            return _clean(-number if op == "-" else number)
        return self._primary()

    def _primary(self) -> Any:
        token = self._next()

        if token.kind == "number":
            return _clean(token.value)

        if token.kind == "string":
            if self._mode != "string":
                raise FormulaError("数字公式里不能出现文本字面量（如需拼接请把公式类型改为「文本拼接」）")
            return token.value

        if token.kind == "ident":
            name = token.value
            if self._accept_op("(") is not None:
                if self._mode == "string":
                    raise FormulaError("文本拼接公式里不能调用函数")
                return self._call(name)
            if self._known_keys is not None and name not in self._known_keys:
                raise FormulaError(f"公式引用了不存在的字段：{name}")
            # 字段已声明但当前没值 → 返回 None，由运算符按 0 / 空串处理
            return self._values.get(name)

        if token.kind == "op" and token.value == "(":
            value = self._expr()
            if self._accept_op(")") is None:
                raise FormulaError("公式缺少右括号")
            return value

        raise FormulaError(f"公式在第 {token.pos} 个字符处出现意外符号：{token.value!r}")

    def _call(self, name: str) -> Any:
        if name not in ALLOWED_FUNCTIONS:
            raise FormulaError(
                f"不支持的函数：{name}（可用：{', '.join(sorted(ALLOWED_FUNCTIONS))}）"
            )

        args: list[Any] = []
        if self._accept_op(")") is None:
            args.append(self._expr())
            while self._accept_op(",") is not None:
                args.append(self._expr())
            if self._accept_op(")") is None:
                raise FormulaError(f"{name}() 缺少右括号")

        nums: list[Decimal] = []
        for arg in args:
            number = _to_decimal(arg)
            if number is None:
                raise FormulaError(f"{name}() 的参数必须是数字")
            nums.append(number)

        if name == "ROUND":
            if len(nums) != 2:
                raise FormulaError("ROUND() 需要 2 个参数：ROUND(值, 小数位)")
            # 显式四舍五入：Decimal 默认 ROUND_HALF_EVEN（银行家舍入），
            # ROUND(2.5, 0) 会得 2，与金额场景预期（3）不符
            quantum = Decimal(1).scaleb(-int(nums[1]))
            return _clean(nums[0].quantize(quantum, rounding=ROUND_HALF_UP))
        if name == "ABS":
            if len(nums) != 1:
                raise FormulaError("ABS() 需要 1 个参数")
            return _clean(abs(nums[0]))
        if name == "MIN":
            if not nums:
                raise FormulaError("MIN() 至少需要 1 个参数")
            return _clean(min(nums))
        if name == "MAX":
            if not nums:
                raise FormulaError("MAX() 至少需要 1 个参数")
            return _clean(max(nums))
        raise FormulaError(f"不支持的函数：{name}")

    # ---- 运算 ----

    def _apply_additive(self, op: str, left: Any, right: Any) -> Any:
        if self._mode == "string":
            # 字符串模式：+ 恒为拼接，- 无意义
            if op == "-":
                raise FormulaError("文本拼接公式里不能使用减号")
            return _stringify(left) + _stringify(right)

        # 数值模式：缺失值按 0，不做字符串拼接
        left_num = _to_decimal(left) or Decimal(0)
        right_num = _to_decimal(right) or Decimal(0)
        return _clean(left_num + right_num if op == "+" else left_num - right_num)

    @staticmethod
    def _apply_multiplicative(op: str, left: Any, right: Any) -> Any:
        left_num = _to_decimal(left) or Decimal(0)
        right_num = _to_decimal(right) or Decimal(0)

        if op == "*":
            return _clean(left_num * right_num)
        if right_num == 0:
            # 除零返回 None 而不是抛错：表单填一半时不该让整页报错
            return None
        if op == "/":
            return _clean(left_num / right_num)
        return _clean(left_num % right_num)


# --------------------------------------------------------------------------- 日期差


def _to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("/", "-")
        try:  # 兜底：ISO 格式（可能带毫秒/时区）
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None
    return None


# --------------------------------------------------------------------------- 入口


def evaluate_arithmetic(
    expression: str,
    values: Mapping[str, Any],
    *,
    known_keys: Collection[str] | None = None,
) -> Any:
    """数值模式求值。缺失字段按 0；语法/引用错误抛 `FormulaError`。

    `known_keys` 给了就是严格模式：引用 schema 里没声明的字段会报错。
    """
    if not expression or not expression.strip():
        return None
    return _Parser(_tokenize(expression), values, mode="numeric", known_keys=known_keys).parse()


def evaluate_concat(
    expression: str,
    values: Mapping[str, Any],
    *,
    known_keys: Collection[str] | None = None,
) -> Any:
    """字符串模式求值。缺失字段按空串；`+` 恒为拼接。"""
    if not expression or not expression.strip():
        return None
    return _Parser(_tokenize(expression), values, mode="string", known_keys=known_keys).parse()


def evaluate_formula(
    formula: FieldFormula,
    values: Mapping[str, Any],
    *,
    subtable_rows: Mapping[str, list[Mapping[str, Any]]] | None = None,
    known_keys: Collection[str] | None = None,
) -> Any:
    """按公式类型求值。任何失败返回 None（表单不该因为公式算不出来而崩）。

    `subtable_rows` 提供 `{子表字段key: [行, ...]}`，用于 `subtable_sum`。
    `known_keys` 见 `evaluate_arithmetic`。
    """
    try:
        if formula.type is FormulaType.ARITHMETIC:
            return evaluate_arithmetic(
                formula.expression or "", values, known_keys=known_keys
            )
        if formula.type is FormulaType.CONCAT:
            return evaluate_concat(formula.expression or "", values, known_keys=known_keys)

        if formula.type is FormulaType.SUBTABLE_SUM:
            rows = (subtable_rows or {}).get(formula.subtable_key or "", [])
            total = Decimal(0)
            for row in rows:
                cell = _to_decimal(row.get(formula.column_key or ""))
                if cell is not None:
                    total += cell
            return _clean(total)

        if formula.type is FormulaType.DATE_DIFF:
            start = _to_date(values.get(formula.start_field or ""))
            end = _to_date(values.get(formula.end_field or ""))
            if start is None or end is None:
                return None
            return (end - start).days

    except FormulaError:
        return None
    return None


def _collect_subtable_rows(
    schema: Any, values: Mapping[str, Any]
) -> dict[str, list[Mapping[str, Any]]]:
    rows: dict[str, list[Mapping[str, Any]]] = {}
    for section in schema.sections:
        for field in section.fields:
            if field.type.value != "subtable":
                continue
            raw = values.get(field.key)
            if isinstance(raw, list):
                rows[field.key] = [r for r in raw if isinstance(r, Mapping)]
    return rows


def evaluate_schema_formulas(schema: Any, values: dict[str, Any]) -> dict[str, Any]:
    """把一份 schema 里所有公式字段重算一遍，返回需要覆盖的 `{key: 新值}`。

    服务端在提交时调用它做权威重算（决策 D4）：前端算出来的值一律被这里覆盖，
    防止绕过前端校验伪造计算结果。

    **两趟执行**，避免依赖字段在 schema 中的书写顺序：
      1. 先算子表行内公式，把结果回填进 `subtable_rows`
      2. 再算顶层公式 —— 此时「子表合计」才能看到已算好的行内小计
    """
    updates: dict[str, Any] = {}
    subtable_rows = _collect_subtable_rows(schema, values)

    subtables: list[Any] = []
    top_level_fields: list[Any] = []
    top_known: set[str] = set()
    for section in schema.sections:
        for field in section.fields:
            top_known.add(field.key)
            if field.type.value == "subtable":
                subtables.append(field)
            elif field.formula is not None:
                top_level_fields.append(field)

    # 第一趟：子表行内公式逐行计算。
    # 行内公式的作用域是本子表的列，所以 known_keys 只给列名。
    for subtable in subtables:
        formula_cols = [c for c in subtable.columns if c.formula is not None]
        rows = subtable_rows.get(subtable.key)
        if not formula_cols or not rows:
            continue
        column_keys = {c.key for c in subtable.columns}
        new_rows: list[dict[str, Any]] = []
        for row in rows:
            computed = dict(row)
            for col in formula_cols:
                computed[col.key] = evaluate_formula(
                    col.formula,
                    computed,
                    subtable_rows=subtable_rows,
                    known_keys=column_keys,
                )
            new_rows.append(computed)
        # 回填，让第二趟的「子表合计」能看到已算好的行内小计
        subtable_rows[subtable.key] = new_rows
        updates[subtable.key] = new_rows

    # 第二趟：顶层公式
    for field in top_level_fields:
        updates[field.key] = evaluate_formula(
            field.formula, values, subtable_rows=subtable_rows, known_keys=top_known
        )

    return updates
