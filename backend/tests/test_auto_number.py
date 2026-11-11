"""表单字段自动编号：标识位 + YYYYMMDD + 当日流水号。"""

from __future__ import annotations

from datetime import date

from app.core.idgen import auto_number_values, next_auto_number
from app.schemas.form_schema import parse_form_schema, validate_form_schema


def _schema(*fields: dict) -> object:
    return parse_form_schema(
        {"sections": [{"key": "sec", "title": "申请", "fields": list(fields)}]}
    )


def test_next_auto_number_daily_sequence(db):
    day = date(2026, 11, 11)
    first = next_auto_number(db, prefix="REQ", on_date=day)
    second = next_auto_number(db, prefix="REQ", on_date=day)
    other = next_auto_number(db, prefix="BX", on_date=day)
    next_day = next_auto_number(db, prefix="REQ", on_date=date(2026, 11, 12))

    assert first == "REQ202611110001"
    assert second == "REQ202611110002"
    assert other == "BX202611110001"
    assert next_day == "REQ202611120001"


def test_auto_number_values_keep_existing(db):
    schema = _schema({
        "key": "code", "label": "编号", "type": "text",
        "auto_number": {"prefix": "DEMO", "seq_length": 3},
    })
    generated = auto_number_values(db, schema, existing={})
    assert generated["code"].startswith("DEMO")
    assert generated["code"].endswith("001")
    assert len(generated["code"]) == len("DEMO") + 8 + 3

    kept = auto_number_values(db, schema, existing={"code": "KEEP-001"})
    assert kept["code"] == "KEEP-001"


def test_auto_number_schema_rules() -> None:
    ok = _schema({
        "key": "code", "label": "编号", "type": "text",
        "auto_number": {"prefix": "REQ"},
    })
    assert [i for i in validate_form_schema(ok) if i.severity == "error"] == []

    wrong_type = _schema({
        "key": "code", "label": "编号", "type": "number",
        "auto_number": {"prefix": "REQ"},
    })
    assert "AUTO_NUMBER_TYPE" in {i.code for i in validate_form_schema(wrong_type)}

    conflict = _schema({
        "key": "code", "label": "编号", "type": "text",
        "auto_number": {"prefix": "REQ"}, "default_source": "initiator",
    })
    codes = {i.code for i in validate_form_schema(conflict)}
    assert "AUTO_NUMBER_CONFLICT" in codes
