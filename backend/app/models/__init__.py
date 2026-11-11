"""ORM 模型。

在此集中导入，保证 `Base.metadata` 能看到全部表 —— Alembic 的 autogenerate
和测试里的 `create_all()` 都依赖这一点。
"""

from app.db.base import Base
from app.models.attachment import Attachment
from app.models.audit import (
    AuditLog,
    DataSnapshot,
    EngineEventRecord,
    InstanceAction,
    Notification,
)
from app.models.flow import FlowTemplate, FlowVersion
from app.models.form import FormTemplate, FormVersion
from app.models.instance import FlowInstance, InstanceExtField
from app.models.number import GeneratedNumber
from app.models.org import Department, Role, User, UserRole
from app.models.task import Task, TaskAssignment
from app.models.work_stat import WorkStatRow, WorkStatRowLog, WorkStatSheet

__all__ = [
    "Attachment",
    "AuditLog",
    "Base",
    "DataSnapshot",
    "Department",
    "EngineEventRecord",
    "FlowInstance",
    "FlowTemplate",
    "FlowVersion",
    "FormTemplate",
    "FormVersion",
    "GeneratedNumber",
    "InstanceAction",
    "InstanceExtField",
    "Notification",
    "Role",
    "Task",
    "TaskAssignment",
    "User",
    "UserRole",
    "WorkStatRow",
    "WorkStatRowLog",
    "WorkStatSheet",
]
