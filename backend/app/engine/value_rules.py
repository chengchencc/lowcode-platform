"""字段值的服务端校验（PRD F1.7 / 决策 D4）。

**为什么必须有这一层**：前端 `src/utils/formValue.ts` 的 `validateValues`
只做即时提示，而接口是能被直接调用的 —— 规则只写在浏览器里等于没有规则。
本模块与前端的规则一一对应（同样的判定、同样的提示语），
差异由 `tests/test_value_rules.py` 的用例固定住。

与 `app/engine/validate.py` 的分工：
- `validate.py`：**流程定义**的合法性（发布时检查，面向设计者）
- 本模块：**字段值**的合法性（提交/处理时检查，面向填写者）

只校验「本次由这个人负责的字段」（`only_keys`）—— 别人填过的、或者本节点
看不到的字段留着旧值，不该拦住这次提交。
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from app.core.constants import DISPLAY_FIELD_TYPES

#: 值必须是已配选项之一的控件
_OPTION_TYPES = frozenset({"select", "radio"})
#: 多值且每项都必须是已配选项
_MULTI_OPTION_TYPES = frozenset({"checkbox"})
_TEXT_TYPES = frozenset({"text", "textarea"})
_FILE_TYPES = frozenset({"attachment", "image"})

_MISSING: tuple[Any, ...] = (None, "", [])


@dataclass(frozen=True, slots=True)
class ValueIssue:
    """一条校验不通过。`key` 是字段引用（子表列是 `表.列`），前端据此高亮。"""

    key: str
    label: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label, "message": self.message}


def validate_values(
    form_schema: Any,
    values: Mapping[str, Any],
    *,
    only_keys: Collection[str] | None = None,
) -> list[ValueIssue]:
    """校验字段值。`only_keys` 给了就只校验这些字段引用，否则全量。"""
    issues: list[ValueIssue] = []
    allowed = None if only_keys is None else set(only_keys)

    for section in form_schema.sections:
        for field in section.fields:
            if field.type in DISPLAY_FIELD_TYPES:
                # 展示控件不绑定数据，没有值可校验
                continue
            if field.type == "formula":
                # 公式值由服务端重算，不接受外部传入，也就没什么可校验的
                continue
            if allowed is not None and field.key not in allowed:
                continue
            if field.type == "subtable":
                _check_subtable(field, values.get(field.key), values, issues, allowed)
                continue
            _check_field(
                field,
                values.get(field.key),
                values,
                key=field.key,
                label=field.label,
                issues=issues,
            )

    return issues


def _check_field(
    field: Any,
    value: Any,
    values: Mapping[str, Any],
    *,
    key: str,
    label: str,
    issues: list[ValueIssue],
) -> None:
    """单个控件。子表列复用它，此时 key/label 换成带行号的那份。"""
    if value in _MISSING:
        return

    validators = getattr(field, "validators", None)
    field_type = field.type.value if hasattr(field.type, "value") else str(field.type)

    if field_type in _TEXT_TYPES:
        _check_text(key, label, str(value), validators, issues)

    elif field_type == "number":
        _check_number(key, label, value, validators, issues)

    elif field_type in _OPTION_TYPES:
        _check_in_options(field, key, label, [value], issues)

    elif field_type in _MULTI_OPTION_TYPES:
        if not isinstance(value, (list, tuple)):
            issues.append(ValueIssue(key, label, f"{label}的值必须是列表"))
        else:
            _check_in_options(field, key, label, list(value), issues)

    elif field_type == "cascader":
        _check_cascader(field, value, values, key=key, label=label, issues=issues)

    elif field_type in _FILE_TYPES:
        count = len(value) if isinstance(value, (list, tuple)) else 1
        max_count = getattr(validators, "max_file_count", None)
        # 单个文件的大小在**上传时**就挡住了，这里只数个数
        if max_count is not None and count > max_count:
            issues.append(ValueIssue(key, label, f"{label}最多 {max_count} 个文件"))


def _check_text(
    key: str, label: str, text: str, validators: Any, issues: list[ValueIssue]
) -> None:
    min_length = getattr(validators, "min_length", None)
    max_length = getattr(validators, "max_length", None)
    if min_length is not None and len(text) < min_length:
        issues.append(ValueIssue(key, label, f"{label}至少 {min_length} 个字符"))
    if max_length is not None and len(text) > max_length:
        issues.append(ValueIssue(key, label, f"{label}最多 {max_length} 个字符"))
    pattern = getattr(validators, "regex", None)
    if not pattern:
        return
    try:
        matched = re.fullmatch(pattern, text) is not None
    except re.error:
        # 设计器里的正则可能还没写对 —— 那是模板的问题，不该拦住填写者
        return
    if not matched:
        issues.append(ValueIssue(key, label, f"{label}格式不正确"))


def _check_number(
    key: str, label: str, value: Any, validators: Any, issues: list[ValueIssue]
) -> None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        issues.append(ValueIssue(key, label, f"{label}必须是数字"))
        return
    minimum = getattr(validators, "min", None)
    maximum = getattr(validators, "max", None)
    if minimum is not None and num < minimum:
        issues.append(ValueIssue(key, label, f"{label}不能小于 {_num(minimum)}"))
    if maximum is not None and num > maximum:
        issues.append(ValueIssue(key, label, f"{label}不能大于 {_num(maximum)}"))


def _check_in_options(
    field: Any, key: str, label: str, incoming: list[Any], issues: list[ValueIssue]
) -> None:
    options = getattr(field, "options", None) or []
    if not options:
        # 没配选项的控件（设计器允许）不做限制，否则谁也别想提交
        return
    allowed = {_key_of(o.value) for o in options}
    for item in incoming:
        if _key_of(item) not in allowed:
            issues.append(ValueIssue(key, label, f"{label}的取值不在选项里"))
            return


def _check_cascader(
    field: Any,
    value: Any,
    values: Mapping[str, Any],
    *,
    key: str,
    label: str,
    issues: list[ValueIssue],
) -> None:
    """级联下拉：值的合法性由**父字段的当前值**决定（PRD §3.2.2）。

    「父字段改了、子值没跟着改」是最常见的脏数据来源 ——
    前端会在父值变化时清空子值，服务端这里负责拦住绕过前端的调用。
    """
    config = getattr(field, "cascader", None)
    if config is None:
        return
    parent_value = values.get(config.parent_field)
    if parent_value in _MISSING:
        issues.append(ValueIssue(key, label, f"请先选择{label}的上级选项"))
        return
    options = (config.options_by_parent or {}).get(str(parent_value)) or []
    if not options:
        issues.append(ValueIssue(key, label, f"{label}在上级选项下没有可选值"))
        return
    if _key_of(value) not in {_key_of(o.value) for o in options}:
        issues.append(ValueIssue(key, label, f"{label}与上级选项不匹配"))


def _check_subtable(
    field: Any,
    rows: Any,
    values: Mapping[str, Any],
    issues: list[ValueIssue],
    allowed: set[str] | None,
) -> None:
    columns = list(getattr(field, "columns", None) or [])
    if not isinstance(rows, (list, tuple)):
        if rows not in _MISSING:
            issues.append(ValueIssue(field.key, field.label, f"{field.label}必须是明细行列表"))
        return

    validators = getattr(field, "validators", None)
    min_rows = getattr(validators, "min_rows", None)
    max_rows = getattr(validators, "max_rows", None)
    if min_rows is not None and len(rows) < min_rows:
        issues.append(ValueIssue(field.key, field.label, f"{field.label}至少 {min_rows} 行"))
    if max_rows is not None and len(rows) > max_rows:
        issues.append(ValueIssue(field.key, field.label, f"{field.label}最多 {max_rows} 行"))

    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        # 行内的级联列要看**同一行**的父列，而不是外面的字段
        for column in columns:
            if column.type == "formula":
                continue
            ref = f"{field.key}.{column.key}"
            if allowed is not None and ref not in allowed:
                continue
            _check_field(
                column,
                row.get(column.key),
                row,
                key=ref,
                label=f"第 {index + 1} 行的「{column.label}」",
                issues=issues,
            )


def _key_of(value: Any) -> str:
    """选项值可能是 str/int/float/bool，比较前统一成字符串。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _num(value: float) -> str:
    """1.0 显示成 1 —— 别让用户看到浮点尾巴。"""
    return str(int(value)) if float(value).is_integer() else str(value)
