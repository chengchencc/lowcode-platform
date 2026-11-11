"""业务编号生成。

形如 `LX20260922-0001`：前缀 + 日期 + 当日流水号。

**并发**：流水号靠「查当日最大号 +1」，天然有竞态。这里不靠锁，
而是依赖 `flow_instances.code` 的唯一约束 —— 撞了就重试。
对一个日流水几十条的内部系统，这比维护一张计数表更简单，
也比在事务里锁住一整天的号段并发度好。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError

#: 编号前缀，可按业务含义区分（请假 QJ / 报销 BX …）
DEFAULT_PREFIX = "LX"

#: 单次生成的日期格式
_DATE_FMT = "%Y%m%d"

MAX_RETRY = 5


def next_code(db: Session, *, prefix: str = DEFAULT_PREFIX, on_date: date | None = None) -> str:
    """生成下一个编号（不落库，调用方负责插入）。"""
    from app.models import FlowInstance

    day = (on_date or date.today()).strftime(_DATE_FMT)
    like = f"{prefix}{day}-%"
    latest = db.scalar(
        select(func.max(FlowInstance.code)).where(FlowInstance.code.like(like))
    )
    seq = 1
    if latest:
        try:
            seq = int(latest.rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            # 历史脏数据（不符合编号格式）不该让新建流程失败
            seq = 1
    return f"{prefix}{day}-{seq:04d}"


def next_auto_number(
    db: Session,
    *,
    prefix: str,
    seq_length: int = 4,
    on_date: date | None = None,
) -> str:
    """生成表单字段的自动编号：标识位 + YYYYMMDD + 当日流水号。

    与实例编号同一套并发策略：查当日最大流水 +1，靠 `generated_numbers.number`
    的唯一约束重试；重试用 SAVEPOINT，不破坏调用方事务。
    """
    from app.models import GeneratedNumber

    day = (on_date or date.today()).strftime(_DATE_FMT)
    last_error: Exception | None = None
    for _ in range(MAX_RETRY):
        latest = db.scalar(
            select(func.max(GeneratedNumber.seq)).where(
                GeneratedNumber.prefix == prefix,
                GeneratedNumber.seq_date == day,
            )
        )
        seq = (latest or 0) + 1
        number = f"{prefix}{day}{seq:0{seq_length}d}"
        try:
            with db.begin_nested():
                db.add(GeneratedNumber(number=number, prefix=prefix, seq_date=day, seq=seq))
                db.flush()
            return number
        except IntegrityError as exc:
            last_error = exc
            continue
    raise ConflictError(
        "生成表单编号失败，请重试", code="NUMBER_GENERATION_FAILED"
    ) from last_error


def auto_number_values(
    db: Session,
    form_schema,
    existing: Mapping[str, object] | None = None,
) -> dict[str, str]:
    """按 schema 的 `auto_number` 配置算出编号（已有编号保持不变）。"""
    existing = existing or {}
    out: dict[str, str] = {}
    for section in form_schema.sections:
        for field in section.fields:
            config = getattr(field, "auto_number", None)
            if config is None:
                continue
            current = existing.get(field.key)
            if current not in (None, ""):
                out[field.key] = str(current)
            else:
                out[field.key] = next_auto_number(
                    db, prefix=config.prefix, seq_length=config.seq_length
                )
    return out


def create_with_code(db: Session, factory, *, prefix: str = DEFAULT_PREFIX):
    """带编号重试地创建一个实例。

    `factory(code)` 接收编号并返回未落库的 ORM 对象；撞唯一约束就重新取号再试。

    重试用 **SAVEPOINT**（`begin_nested`）而不是 `rollback()` ——
    后者会把调用方在本次事务里已经做的工作（写草稿数据、记审计…）一起回滚掉。
    """
    last_error: Exception | None = None
    for _ in range(MAX_RETRY):
        code = next_code(db, prefix=prefix)
        try:
            with db.begin_nested():
                obj = factory(code)
                db.add(obj)
                db.flush()
            return obj
        except IntegrityError as exc:
            # 已被 begin_nested 回滚到保存点，外层事务完好，可以继续重试
            last_error = exc
            continue
    raise ConflictError(
        "生成业务编号失败，请重试", code="CODE_GENERATION_FAILED"
    ) from last_error
