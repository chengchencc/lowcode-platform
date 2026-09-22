"""公式引擎测试（PRD §10 #9）。

用例来自 `docs/formula-test-vectors.json` —— 前后端共享的测试向量（决策 D4）。
前端 `src/utils/formula.ts` 跑同一份文件，任何一侧语义漂移都会被抓出来。

本文件是**纯函数测试**，不需要数据库（engine 的纯核心不得依赖 db）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.constants import FormulaType
from app.engine.expressions import (
    FormulaError,
    evaluate_arithmetic,
    evaluate_formula,
    evaluate_schema_formulas,
)
from app.schemas.form_schema import FieldFormula, parse_form_schema

VECTORS_FILE = Path(__file__).resolve().parents[2] / "docs" / "formula-test-vectors.json"
VECTORS = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))


def _id(case: dict) -> str:
    return case["name"]


@pytest.mark.parametrize("case", VECTORS["vectors"], ids=_id)
def test_formula_vector(case: dict) -> None:
    formula = FieldFormula.model_validate(case["formula"])
    got = evaluate_formula(
        formula, case["values"], subtable_rows=case.get("subtable_rows")
    )
    assert got == case["expected"], f"{case['name']}：期望 {case['expected']!r}，实际 {got!r}"


@pytest.mark.parametrize("case", VECTORS["error_vectors"], ids=_id)
def test_formula_error_vector(case: dict) -> None:
    """这些表达式必须抛错，而不是被静默算成某个值。"""
    formula = FieldFormula.model_validate(case["formula"])
    assert formula.expression, "错误用例应当带表达式"
    with pytest.raises(FormulaError):
        evaluate_arithmetic(
            formula.expression, case["values"], known_keys=case.get("known_keys")
        )


def test_vectors_file_is_wellformed() -> None:
    """防止向量文件本身写坏（改了但没被跑到的用例）。"""
    assert VECTORS["vectors"], "至少要有正常用例"
    assert VECTORS["error_vectors"], "至少要有错误用例"
    names = [c["name"] for c in VECTORS["vectors"] + VECTORS["error_vectors"]]
    assert len(names) == len(set(names)), "用例名称不能重复"


# --------------------------------------------------------------------------- 边界


def test_evaluate_formula_swallows_errors() -> None:
    """求值失败返回 None 而不是抛错 —— 表单填一半时不该让整页崩掉。"""
    # 语法错误
    broken = FieldFormula(type=FormulaType.ARITHMETIC, expression="a * * b")
    assert evaluate_formula(broken, {"a": 1, "b": 2}) is None

    # 严格模式下引用了不存在的字段
    ghost = FieldFormula(type=FormulaType.ARITHMETIC, expression="ghost * 2")
    assert evaluate_formula(ghost, {}, known_keys=set()) is None

    # 不传 known_keys 时是宽松模式：任何缺失标识符都按 0，所以这里得 0 而不是 None
    assert evaluate_formula(ghost, {}) == 0


def test_known_keys_distinguishes_missing_from_unknown() -> None:
    """「字段已声明但没值」与「字段根本不存在」必须区分开。

    前者按 0 处理（用户还没填），后者是配置错误，要报出来。
    """
    # 已声明但没值 → 0
    assert evaluate_arithmetic("a + b", {"a": 5}, known_keys={"a", "b"}) == 5
    # 未声明 → 报错
    with pytest.raises(FormulaError):
        evaluate_arithmetic("a + ghost", {"a": 5}, known_keys={"a", "b"})


def test_empty_expression_returns_none() -> None:
    assert evaluate_arithmetic("", {}) is None
    assert evaluate_arithmetic("   ", {}) is None


def test_boolean_is_not_a_number_in_arithmetic() -> None:
    """开关字段参与四则时应被当作 1/0，而不是报错。"""
    assert evaluate_arithmetic("flag * 10", {"flag": True}) == 10
    assert evaluate_arithmetic("flag * 10", {"flag": False}) == 0


def test_deep_nesting_does_not_blow_up() -> None:
    expr = "((((1 + 2) * 3) + 4) * 5)"
    assert evaluate_arithmetic(expr, {}) == 65


# --------------------------------------------------------------------------- schema 重算


REIMBURSE_SCHEMA = {
    "sections": [
        {
            "key": "sec_apply",
            "title": "申请信息",
            "stage": "apply",
            "fields": [
                {"key": "qty", "label": "数量", "type": "number"},
                {"key": "price", "label": "单价", "type": "number"},
                {
                    "key": "items",
                    "label": "明细",
                    "type": "subtable",
                    "columns": [
                        {"key": "qty", "label": "数量", "type": "number"},
                        {"key": "price", "label": "单价", "type": "number"},
                        {
                            "key": "subtotal",
                            "label": "小计",
                            "type": "formula",
                            "formula": {"type": "arithmetic", "expression": "qty * price"},
                        },
                    ],
                },
                {
                    "key": "total",
                    "label": "合计",
                    "type": "formula",
                    "formula": {
                        "type": "subtable_sum",
                        "subtable_key": "items",
                        "column_key": "subtotal",
                    },
                },
            ],
        }
    ]
}


def test_evaluate_schema_formulas_recomputes_subtable_rows() -> None:
    """服务端权威重算（决策 D4）：子表行内公式逐行算，顶层公式汇总。"""
    schema = parse_form_schema(REIMBURSE_SCHEMA)
    values = {
        "qty": 2,
        "price": 10,
        "items": [
            {"qty": 3, "price": 12.5},   # 37.5
            {"qty": 1, "price": 100},    # 100
        ],
    }

    updates = evaluate_schema_formulas(schema, values)

    assert updates["items"][0]["subtotal"] == 37.5
    assert updates["items"][1]["subtotal"] == 100
    assert updates["total"] == 137.5


def test_evaluate_schema_formulas_ignores_non_formula_fields() -> None:
    schema = parse_form_schema(REIMBURSE_SCHEMA)
    updates = evaluate_schema_formulas(schema, {"qty": 1, "price": 2, "items": []})
    assert "qty" not in updates
    assert updates["total"] == 0


def test_evaluate_schema_formulas_handles_missing_subtable() -> None:
    """子表还没填时不应抛错。"""
    schema = parse_form_schema(REIMBURSE_SCHEMA)
    updates = evaluate_schema_formulas(schema, {})
    assert updates["total"] == 0
