"""表单模型：表单模板 + 表单版本（PRD §3.2）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import FormStatus, FormVersionStatus
from app.db.base import Base, IntType, PkMixin, TimestampMixin


class FormTemplate(Base, PkMixin, TimestampMixin):
    """表单模板主档。字段结构在 `FormVersion.schema` 里，主档只存元信息。

    版本化的原因（PRD §3.1）：流程实例运行期间模板改版不能影响已有实例。
    因此流程版本发布时会**锁定**当时引用的表单版本，实例全程用那一份 schema。
    """

    __tablename__ = "form_templates"

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    #: 业务编码，用于导入导出与人工引用；可为空（同一名称允许多个模板）
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    #: 列表页分组（PRD F1.1）
    group_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FormStatus.DRAFT, index=True
    )

    #: 当前对外生效的版本（最新一个 PUBLISHED）。新建流程版本时会锁定它。
    #: 刻意不建外键：form_templates ↔ form_versions 互相引用会成环，
    #: 环外键在 SQLite 上要靠批处理重建表（同 departments.manager_user_id 的处理）。
    current_version_id: Mapped[int | None] = mapped_column(IntType, nullable=True)

    created_by: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False
    )

    versions: Mapped[list[FormVersion]] = relationship(
        "FormVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="FormVersion.version_no.desc()",
    )

    @property
    def published_version_ids(self) -> list[int]:
        """需要调用方已加载 `versions`。"""
        return [v.id for v in self.versions if v.status == FormVersionStatus.PUBLISHED]


class FormVersion(Base, PkMixin, TimestampMixin):
    """表单版本。一次发布后 `schema` 即冻结，不可再改（要改就新建版本）。

    同一模板同时只允许存在**一个** DRAFT 版本 —— 这是「编辑草稿 → 发布成新版本」
    工作流的保证。该约束由 service 层维护（部分唯一索引在 SQLite / MySQL 上
    不可移植，故不落 DDL）。
    """

    __tablename__ = "form_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version_no", name="uk_fv_template_version"),
    )

    template_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("form_templates.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    #: 结构见 app/schemas/form_schema.py（写入前必过结构校验）
    schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FormVersionStatus.DRAFT, index=True
    )
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    template: Mapped[FormTemplate] = relationship("FormTemplate", back_populates="versions")
