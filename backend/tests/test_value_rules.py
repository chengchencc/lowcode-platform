"""字段值校验的纯核心测试（不碰数据库）。

对应前端 `src/utils/formValue.ts` 的 `validateValues` —— 两边规则必须一致，
差异会在这里和那边的 spec 里同时暴露。
"""

from __future__ import annotations

import pytest

from app.engine.value_rules import validate_values
from app.schemas.form_schema import FormSchema


def schema(fields: list[dict], *, stage: str = "apply") -> FormSchema:
    return FormSchema.model_validate(
        {"sections": [{"key": "s1", "title": "申请", "stage": stage, "fields": fields}]}
    )


def messages(issues) -> list[str]:
    return [i.message for i in issues]


# --------------------------------------------------------------------------- 文本


def test_text_length_and_regex():
    form = schema([{
        "key": "phone", "label": "手机号", "type": "text",
        "validators": {"min_length": 11, "max_length": 11, "regex": r"1\d{10}"},
    }])

    assert validate_values(form, {"phone": "13800138000"}) == []
    assert "手机号至少 11 个字符" in messages(validate_values(form, {"phone": "138"}))
    assert "手机号格式不正确" in messages(validate_values(form, {"phone": "abcdefghijk"}))


def test_invalid_regex_in_template_does_not_block_filling():
    """设计器里正则还没写对时，不该拦填写者 —— 那是模板的问题。"""
    form = schema([{
        "key": "x", "label": "字段", "type": "text", "validators": {"regex": "([unclosed"},
    }])
    assert validate_values(form, {"x": "任意"}) == []


def test_empty_value_skips_rules():
    form = schema([{"key": "x", "label": "字段", "type": "text",
                    "validators": {"min_length": 5}}])
    for empty in (None, "", []):
        assert validate_values(form, {"x": empty}) == []


# --------------------------------------------------------------------------- 数字


def test_number_range():
    form = schema([{"key": "amount", "label": "金额", "type": "number",
                    "validators": {"min": 1, "max": 10000}}])

    assert validate_values(form, {"amount": 100}) == []
    assert messages(validate_values(form, {"amount": 0})) == ["金额不能小于 1"]
    assert messages(validate_values(form, {"amount": 20000})) == ["金额不能大于 10000"]
    # 表单值常是字符串
    assert messages(validate_values(form, {"amount": "0"})) == ["金额不能小于 1"]
    assert messages(validate_values(form, {"amount": "abc"})) == ["金额必须是数字"]


def test_number_message_has_no_float_tail():
    form = schema([{"key": "n", "label": "数量", "type": "number",
                    "validators": {"min": 1.0}}])
    assert messages(validate_values(form, {"n": 0})) == ["数量不能小于 1"]


# --------------------------------------------------------------------------- 选项


def test_option_membership():
    form = schema([{
        "key": "type", "label": "费用类型", "type": "select",
        "options": [{"label": "差旅", "value": "travel"}, {"label": "办公", "value": 2}],
    }])

    assert validate_values(form, {"type": "travel"}) == []
    assert validate_values(form, {"type": 2}) == []          # 数字选项
    assert validate_values(form, {"type": "2"}) == []        # 字符串形式的数字
    assert messages(validate_values(form, {"type": "other"})) == ["费用类型的取值不在选项里"]


def test_multi_select_checks_every_item():
    form = schema([{
        "key": "tags", "label": "标签", "type": "checkbox",
        "options": [{"label": "A", "value": "a"}, {"label": "B", "value": "b"}],
    }])

    assert validate_values(form, {"tags": ["a", "b"]}) == []
    assert messages(validate_values(form, {"tags": ["a", "z"]})) == ["标签的取值不在选项里"]
    assert messages(validate_values(form, {"tags": "a"})) == ["标签的值必须是列表"]


# --------------------------------------------------------------------------- 级联


def cascader_schema() -> FormSchema:
    return schema([
        {"key": "category", "label": "费用类别", "type": "select",
         "options": [{"label": "差旅", "value": "travel"}, {"label": "办公", "value": "office"}]},
        {"key": "sub", "label": "费用明细", "type": "cascader",
         "cascader": {"parent_field": "category", "options_by_parent": {
             "travel": [{"label": "机票", "value": "flight"},
                        {"label": "住宿", "value": "hotel"}],
             "office": [{"label": "打印", "value": "print"}],
         }}},
    ])


def test_cascader_value_must_match_parent():
    form = cascader_schema()

    assert validate_values(form, {"category": "travel", "sub": "flight"}) == []
    issues = validate_values(form, {"category": "office", "sub": "flight"})
    assert messages(issues) == ["费用明细与上级选项不匹配"]
    assert issues[0].key == "sub"


def test_cascader_without_parent_selected():
    form = cascader_schema()
    assert messages(validate_values(form, {"sub": "flight"})) == ["请先选择费用明细的上级选项"]


def test_cascader_parent_without_options():
    """上级选了、但这个上级没有配任何子选项 —— 提示要说清楚是哪一种。"""
    form = schema([
        {"key": "category", "label": "费用类别", "type": "select",
         "options": [{"label": "差旅", "value": "travel"}, {"label": "其他", "value": "other"}]},
        {"key": "sub", "label": "费用明细", "type": "cascader",
         "cascader": {"parent_field": "category",
                      "options_by_parent": {"travel": [{"label": "机票", "value": "flight"}]}}},
    ])
    issues = validate_values(form, {"category": "other", "sub": "flight"})
    assert messages(issues) == ["费用明细在上级选项下没有可选值"]


# --------------------------------------------------------------------------- 子表


def subtable_schema() -> FormSchema:
    return schema([{
        "key": "items", "label": "费用明细", "type": "subtable",
        "validators": {"min_rows": 1, "max_rows": 3},
        "columns": [
            {"key": "name", "label": "项目", "type": "text", "required": True,
             "validators": {"max_length": 10}},
            {"key": "amount", "label": "金额", "type": "number",
             "validators": {"min": 0.01}},
            {"key": "subtotal", "label": "小计", "type": "formula",
             "formula": {"type": "arithmetic", "expression": "amount"}},
        ],
    }])


def test_subtable_row_count():
    form = subtable_schema()
    assert messages(validate_values(form, {"items": []})) == ["费用明细至少 1 行"]
    too_many = [{"name": "x", "amount": 1}] * 4
    assert messages(validate_values(form, {"items": too_many})) == ["费用明细最多 3 行"]


def test_subtable_cell_rules_carry_row_number():
    form = subtable_schema()
    issues = validate_values(form, {"items": [
        {"name": "机票", "amount": 1},
        {"name": "这是一条特别长的项目名称", "amount": 0},
    ]})

    assert issues[0].label == "第 2 行的「项目」"
    assert issues[0].message == "第 2 行的「项目」最多 10 个字符"
    assert issues[1].message == "第 2 行的「金额」不能小于 0.01"
    # 引用是「表.列」，前端照它高亮到具体单元格
    assert issues[0].key == "items.name"


def test_subtable_formula_column_is_skipped():
    """小计的公式依赖行内其他列，不该被当成用户填的值来校验。"""
    form = subtable_schema()
    assert validate_values(form, {"items": [{"name": "机票", "amount": 100}]}) == []


def test_subtable_row_cascader_uses_same_row():
    """行内级联要看同一行的父列，而不是表单上的同名字段。"""
    form = schema([{
        "key": "items", "label": "明细", "type": "subtable",
        "columns": [
            {"key": "category", "label": "类别", "type": "select",
             "options": [{"label": "差旅", "value": "travel"}]},
            {"key": "sub", "label": "细项", "type": "cascader",
             "cascader": {"parent_field": "category", "options_by_parent": {
                 "travel": [{"label": "机票", "value": "flight"}]}}},
        ],
    }])

    assert validate_values(form, {"items": [{"category": "travel", "sub": "flight"}]}) == []
    issues = validate_values(form, {"items": [{"category": "travel", "sub": "hotel"}]})
    assert messages(issues) == ["第 1 行的「细项」与上级选项不匹配"]


# --------------------------------------------------------------------------- 其他


def test_only_keys_limits_scope():
    form = schema([
        {"key": "a", "label": "A", "type": "number", "validators": {"min": 10}},
        {"key": "b", "label": "B", "type": "number", "validators": {"min": 10}},
    ])
    values = {"a": 1, "b": 1}

    assert messages(validate_values(form, values, only_keys={"a"})) == ["A不能小于 10"]
    assert validate_values(form, values, only_keys={"c"}) == []


def test_attachment_count():
    form = schema([{"key": "files", "label": "发票", "type": "attachment",
                    "validators": {"max_file_count": 2}}])

    assert validate_values(form, {"files": [1, 2]}) == []
    assert messages(validate_values(form, {"files": [1, 2, 3]})) == ["发票最多 2 个文件"]


def test_formula_field_never_validated():
    form = schema([{"key": "total", "label": "总额", "type": "formula",
                    "formula": {"type": "arithmetic", "expression": "1"},
                    "validators": {"min": 100}}])
    assert validate_values(form, {"total": 0}) == []


def test_unknown_keys_are_ignored():
    """被删掉的字段、前端多发的键都不该让提交失败。"""
    form = schema([{"key": "a", "label": "A", "type": "text"}])
    assert validate_values(form, {"a": "x", "already_removed": 123}) == []


@pytest.mark.parametrize("value", [0, "0", False])
def test_falsey_but_present_values_are_validated(value):
    """0 与 False 是合法值，不能被当成「没填」跳过校验。"""
    form = schema([{"key": "n", "label": "N", "type": "number", "validators": {"min": -1}}])
    assert validate_values(form, {"n": value}) == []
