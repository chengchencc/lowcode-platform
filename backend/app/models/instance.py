"""流程实例与实例级动态字段（PRD §3.1 / §3.4 机制 C）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import InstanceStatus
from app.db.base import Base, CreatedAtMixin, IntType, PkMixin, TimestampMixin


class FlowInstance(Base, PkMixin, TimestampMixin):
    """一次业务办理。

    **数据累积**（PRD §3.4 末尾的实现提示）由三者组合而成：
      · `data_schema`  实例 schema = 模板 schema ⊕ 动态追加字段定义
      · `current_data` 模板字段值 ⊕ 扩展字段值（key 同命名空间，ext_ 前缀防冲突）
      · `field_meta`   每个值的来源追踪（哪个节点、谁、何时写入）

    历史时点的数据在 `data_snapshots`（全量快照）。
    """

    __tablename__ = "flow_instances"

    #: 业务编号，如 LX20260922-0001
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    flow_template_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_templates.id"), nullable=False, index=True
    )
    flow_version_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_versions.id"), nullable=False, index=True
    )
    #: 冗余自 flow_version.locked_form_version_id，避免渲染时多一次 join
    form_version_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("form_versions.id"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    initiator_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False, index=True
    )
    initiator_dept_id: Mapped[int | None] = mapped_column(IntType, nullable=True, index=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=InstanceStatus.DRAFT, index=True
    )
    #: 重新提交轮次（PRD §3.5.1）
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    data_schema: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    current_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    field_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: 动态字段序号，生成 ext_{seq}_{slug} 用
    ext_field_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: 冗余：当前活跃节点 key 列表，列表页展示用（避免逐行查 tasks）
    current_node_keys: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    #: 存在未命中审批人的异常任务
    abnormal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terminated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    #: 乐观锁（决策 D5）。引擎每次变更在事务内锁行，客户端可用它做冲突检测
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    ext_fields: Mapped[list[InstanceExtField]] = relationship(
        "InstanceExtField", back_populates="instance", cascade="all, delete-orphan"
    )


class InstanceExtField(Base, PkMixin, TimestampMixin):
    """实例级动态追加字段（PRD §3.4 机制 C，排期 M5）。

    约束：只作用于该实例、不入模板、追加后不可物理删除（只能停用/隐藏）、
    仅支持基础控件（文本/数字/日期/下拉/附件），不支持子表/公式。
    """

    __tablename__ = "instance_ext_fields"
    __table_args__ = (
        UniqueConstraint("instance_id", "field_key", name="uk_ief_instance_field"),
    )

    instance_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_instances.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    #: 全局唯一 key，生成规则 ext_{seq}_{slug}
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(24), nullable=False)
    #: 归入哪个分区（缺省用虚拟分区 'ext'）
    section_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: 可编辑的节点 id 列表
    editable_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    #: 从哪个节点起可见（之前不可见）
    visible_from_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: ACTIVE / DISABLED —— 不可物理删除（PRD F5.3）
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    source_node_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False
    )

    instance: Mapped[FlowInstance] = relationship("FlowInstance", back_populates="ext_fields")


class InstanceFieldValue(Base, PkMixin, CreatedAtMixin):
    """实例业务字段值索引（M13）。

    JSON 仍是唯一事实源；本表是可重建的派生读模型，只为筛选查询服务。
    """

    __tablename__ = "instance_field_values"
    __table_args__ = (
        UniqueConstraint("instance_id", "field_key", "value_index", name="uk_ifv_instance_field_idx"),
        Index("ix_ifv_field_text", "field_key", "value_text", "instance_id"),
        Index("ix_ifv_field_num", "field_key", "value_num", "instance_id"),
        Index("ix_ifv_field_kind", "field_key", "value_kind", "instance_id"),
    )

    instance_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_instances.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    value_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    value_text: Mapped[str | None] = mapped_column(String(512), nullable=True)
    value_num: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    #: 多选序号；单值/空值固定 0
    value_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
