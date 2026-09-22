"""公式表达式的语法级工具。

放在 `core` 是为了让 `schemas/form_schema.py`（校验器）与
`engine/expressions.py`（求值器）都能用 —— 前者不该依赖后者，
否则 `engine` 反过来导入 `schemas.form_schema.FieldFormula` 就成环了。
"""

from __future__ import annotations

import re

#: 字段/函数名：字母或下划线开头
IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: 字符串字面量（单双引号，支持反斜杠转义）
STRING_LITERAL_PATTERN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def strip_string_literals(expression: str) -> str:
    """把字符串字面量替换成空串，供扫描字段引用时使用。

    否则 `a + "-" + b` 里的内容会被误当成字段名 ——
    例如 `name + "abc"` 里的 `abc` 会被报告成「引用了不存在的字段」。
    """
    return STRING_LITERAL_PATTERN.sub('""', expression)
