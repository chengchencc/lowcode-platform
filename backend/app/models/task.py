"""任务层：token + 每人任务实例（PRD §3.5 / §6）。

**令牌模型在这里落地**：

    一个待办令牌 = tasks 里一行 status='PENDING' AND blocks_flow=1 的记录

- 会签/或签：**一个 task + N 个 assignment**（同节点多人并行）
- 并行组：**N 个 task**（同 group_id）—— 每个成员节点一个令牌
- 依次审批：一个 task + N 个 assignment，只有最小 seq 是 PENDING，其余 WAITING
- 抄送：一个 task（blocks_flow=0）+ N 个 assignment，不占令牌
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AssignmentStatus, TaskStatus
from app.db.base import Base, IntType, PkMixin, TimestampMixin


class Task(Base, PkMixin, TimestampMixin):
    """一个节点的一次激活（= 一个令牌）。"""

    __tablename__ = "tasks"

    instance_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("flow_instances.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    node_key: Mapped[str] = mapped_column(String(64), nullable=False)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(String(16), nullable=False)

    #: SINGLE / SEQUENTIAL / ALL / ANY；抄送为 NULL
    assignee_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TaskStatus.PENDING, index=True
    )
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: 同节点在本轮内第几次激活 —— 退回重派会 +1（用于区分同一节点的多次任务）
    activation_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: 分支决策链，如 ["s2:s2a"]。令牌定位与祖先判定的唯一依据
    gates: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    #: 并行组标识（组内成员共享），非组内为 NULL
    group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    #: 冻结的节点定义快照（含字段权限与审批人规则）——
    #: 流程模板改版不影响已生成的令牌
    node_def_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    #: 审批人解析结果快照：[{"userId": 3, "via": "role:财务"}]
    approver_resolved: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    #: 抄送 = 0：不占令牌、不计进度、不参与聚合（PRD §3.3.2）
    blocks_flow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: 审批人未命中 → 转管理员并标记异常
    abnormal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    abnormal_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    deadline_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    assignments: Mapped[list[TaskAssignment]] = relationship(
        "TaskAssignment", back_populates="task", cascade="all, delete-orphan",
        order_by="TaskAssignment.seq",
    )

    @property
    def is_active_token(self) -> bool:
        """活跃令牌 = 待办 且 阻塞主线。抄送与已完成/已取消的都不是。"""
        return self.status == TaskStatus.PENDING and self.blocks_flow


class TaskAssignment(Base, PkMixin, TimestampMixin):
    """每人任务实例。并行派发时一个 task 对应多行。"""

    __tablename__ = "task_assignments"
    __table_args__ = (
        # ★ 派发幂等：同一任务不会重复派给同一个人
        UniqueConstraint("task_id", "user_id", "seq", name="uk_ta_task_user_seq"),
    )

    task_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: 冗余 instance_id —— 「我的待办/已办」由此单表可查，不必 join tasks
    instance_id: Mapped[int] = mapped_column(IntType, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False, index=True
    )
    #: 依次审批的顺序
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AssignmentStatus.PENDING, index=True
    )
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: [attachmentId, ...]
    attachments: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    #: 该动作产生的 instance_actions.id
    action_id: Mapped[int | None] = mapped_column(IntType, nullable=True)

    # ---- 转办 / 委托（M14）----
    #: 来源用户：转办是原处理人，委托是委托人
    origin_user_id: Mapped[int | None] = mapped_column(IntType, nullable=True, index=True)
    #: TRANSFER / DELEGATION
    origin_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    origin_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 抄送专用
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    task: Mapped[Task] = relationship("Task", back_populates="assignments")
