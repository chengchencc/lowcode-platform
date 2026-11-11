"""委托代理（M14）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import DelegationStatus
from app.db.base import Base, IntType, PkMixin, TimestampMixin


class Delegation(Base, PkMixin, TimestampMixin):
    """用户在指定时段内把审批任务交给他人代理。"""

    __tablename__ = "delegations"

    delegator_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False, index=True
    )
    delegatee_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False, index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    #: 限定流程模板 id 列表；空/None = 全部流程
    flow_template_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DelegationStatus.ACTIVE, index=True
    )
