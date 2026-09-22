"""ORM 模型。

在此集中导入，保证 `Base.metadata` 能看到全部表 —— Alembic 的 autogenerate
和测试里的 `create_all()` 都依赖这一点。
"""

from app.db.base import Base
from app.models.audit import AuditLog
from app.models.org import Department, Role, User, UserRole

__all__ = [
    "AuditLog",
    "Base",
    "Department",
    "Role",
    "User",
    "UserRole",
]
