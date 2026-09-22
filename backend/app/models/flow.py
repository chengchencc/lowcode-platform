"""流程模板与流程版本（PRD §3.3 / §6）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import FlowStatus, FlowVersionStatus
from app.db.base import Base, IntType, PkMixin, TimestampMixin


class FlowTemplate(Base, PkMixin, TimestampMixin):
    """流程模板主档。"""

    __tablename__ = "flow_templates"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    form_template_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("form_templates.id"), nullable=False, index=True
    )
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    #: 发起范围（PRD F2.5）：{"type": "all"} | {"type": "role", "role_ids": [...]}
    #: | {"type": "dept", "dept_ids": [...]}
    initiator_scope: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=lambda: {"type": "all"}
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FlowStatus.DRAFT, index=True
    )
    #: 同 form_templates：与 versions 互相引用会成环，故不建外键
    current_version_id: Mapped[int | None] = mapped_column(IntType, nullable=True)
    created_by: Mapped[int] = mapped_column(IntType, ForeignKey("users.id"), nullable=False)

    versions: Mapped[list[FlowVersion]] = relationship(
        "FlowVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="FlowVersion.version_no.desc()",
    )


class FlowVersion(Base, PkMixin, TimestampMixin):
    """流程版本。

    **发布时锁定表单版本**（PRD F2.6）：实例全程用那一份 schema，
    模板改版不影响运行中的实例。
    """

    __tablename__ = "flow_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version_no", name="uk_flv_template_version"),
    )

    template_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 结构见 app/schemas/flow_definition.py（写入前必过校验）
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: 发布时锁定的表单版本 —— 历史实例靠它取到不可变的 schema
    locked_form_version_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("form_versions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FlowVersionStatus.DRAFT, index=True
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    #: 校验结果快照（F2.7），便于回看「发布时是什么状态」
    validation_report: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[int] = mapped_column(IntType, ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    template: Mapped[FlowTemplate] = relationship("FlowTemplate", back_populates="versions")
