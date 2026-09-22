"""操作审计（F6.6，P1）。追加写，不可修改。"""

from __future__ import annotations

from sqlalchemy import JSON, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin, IntType, PkMixin


class AuditLog(Base, PkMixin, CreatedAtMixin):
    """模板 / 流程 / 组织 / 实例的关键操作留痕。

    没有 updated_at：审计记录只增不改（PRD §7「不可篡改（追加写）」）。
    actor_id 刻意不建外键 —— 用户被删除后审计仍须可读，因此同时冗余 actor_name 快照。
    """

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_biz", "biz_type", "biz_id", "id"),)

    actor_id: Mapped[int | None] = mapped_column(IntType, nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    biz_type: Mapped[str] = mapped_column(String(24), nullable=False)
    biz_id: Mapped[int] = mapped_column(IntType, nullable=False, default=0)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: {"before": {...}, "after": {...}} 的字段级摘要，供追溯
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
