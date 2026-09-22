"""审计与留痕：操作日志、实例动作、数据快照（PRD §3.6 / §6）。

`instance_actions` 与 `data_snapshots` 是引擎的「黑匣子」：
任何一次状态变化与字段写入都留痕，且**只追加不修改**。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CHAR,
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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


class InstanceAction(Base, PkMixin, CreatedAtMixin):
    """实例上发生的一次动作。追加写，不可修改。

    **幂等设计**（PRD §6 / §7「审批动作幂等」）：

    | 键 | 挡什么 |
    |---|---|
    | `uk_ia_request(request_id)` | 客户端网络重试（同一个请求 id 只落一条） |
    | `uk_ia_idem(instance_id, task_id, actor_id, action_seq)` | 同一人在同一任务上重复提交 |

    `task_id` 用 **NOT NULL DEFAULT 0** 而不是可空 + 生成列：
    0 表示「实例级动作」（撤回/终止/追加字段）。生成列在 SQLite 上不支持，
    而「NULL 不参与唯一约束」会让实例级动作的去重失效 —— 两个原因都指向这个设计。
    """

    __tablename__ = "instance_actions"
    __table_args__ = (
        UniqueConstraint(
            "instance_id", "task_id", "actor_id", "action_seq", name="uk_ia_idem"
        ),
        UniqueConstraint("request_id", name="uk_ia_request"),
        Index("ix_ia_instance", "instance_id", "id"),
    )

    instance_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_instances.id", ondelete="CASCADE"), nullable=False
    )
    #: 0 = 实例级动作（撤回/终止/追加字段）
    task_id: Mapped[int] = mapped_column(IntType, nullable=False, default=0)
    #: 仅索引不建外键：instance_actions ↔ task_assignments 互相引用会成环
    assignment_id: Mapped[int | None] = mapped_column(IntType, nullable=True, index=True)

    node_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    node_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False, index=True
    )

    #: SUBMIT / AGREE / REJECT / RETURN / WITHDRAW / ABANDON / TERMINATE /
    #: CC_READ / ADD_EXT_FIELD / DISABLE_EXT_FIELD
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    #: 同一 (实例, 任务, 人) 上的第几次动作，通常为 1（退回后重派才会递增）
    action_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    from_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachments: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    #: [{"key": "amount", "label": "金额", "old": 100, "new": 200}]
    changed_fields: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    #: 客户端幂等键（HTTP 重放）
    request_id: Mapped[str | None] = mapped_column(CHAR(36), nullable=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        IntType, ForeignKey("data_snapshots.id"), nullable=True
    )


class DataSnapshot(Base, PkMixin, CreatedAtMixin):
    """实例数据的全量快照（PRD §3.6「可切换查看每个历史时点的数据快照」）。

    模板 schema 不复制进来 —— `form_versions.schema` 本身不可变，
    快照只需存 `{values, ext_fields}` 就能完整还原某一时刻的表单。
    """

    __tablename__ = "data_snapshots"
    __table_args__ = (
        UniqueConstraint("instance_id", "round", "seq", name="uk_ds_instance_round_seq"),
        Index("ix_ds_instance_time", "instance_id", "created_at"),
    )

    instance_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_instances.id", ondelete="CASCADE"), nullable=False
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: 实例内全局递增序号
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    #: SUBMIT / ACTION / RETURN / REJECT / EXT_FIELD / TERMINATE / ARCHIVE
    kind: Mapped[str] = mapped_column(String(24), nullable=False)

    #: {"values": {...}, "ext_fields": [...]}
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: sha256(values)，便于比对与去重
    data_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)

    #: 仅索引不建外键（instance_actions.snapshot_id 已指向本表，双向 FK 会成环）
    action_id: Mapped[int | None] = mapped_column(IntType, nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(IntType, nullable=False)


class EngineEventRecord(Base, PkMixin, CreatedAtMixin):
    """引擎事件落库（默认关闭，调试期可开）。

    `engine/events.py` 构造的内存事件流是主要形态；这里只是可选的持久化，
    用来排查「为什么流程走到这里停了」这类问题。
    """

    __tablename__ = "engine_events"
    __table_args__ = (Index("ix_ee_instance", "instance_id", "id"),)

    instance_id: Mapped[int] = mapped_column(IntType, nullable=False)
    #: NODE_SPAWNED / TOKEN_CANCELLED / GROUP_JOINED / STATE_CHANGED / ...
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class Notification(Base, PkMixin, CreatedAtMixin):
    """站内消息（PRD F7.1）。

    `dedup_key` 唯一索引让引擎事务重试不产生重复消息 ——
    幂等性一直延伸到通知层。
    """

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("dedup_key", name="uk_notif_dedup"),
        Index("ix_notif_user_read", "user_id", "is_read", "created_at"),
    )

    user_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False, index=True
    )
    #: TASK_CREATED / TASK_CANCELLED / INSTANCE_APPROVED / INSTANCE_REJECTED /
    #: INSTANCE_RETURNED / INSTANCE_WITHDRAWN / INSTANCE_TERMINATED / CC_RECEIVED /
    #: ABNORMAL_ASSIGN
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str | None] = mapped_column(String(512), nullable=True)
    #: {"instance_id": 12, "task_id": 88, ...}
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    #: 前端路由，如 /instance/12?assignment=88
    link: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_read: Mapped[bool] = mapped_column(nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: 幂等去重键，形如 TASK:123:U:5
    dedup_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
