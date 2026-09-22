"""授权判定（PRD §2 角色权限）。

刻意用 Protocol 而不是导入 User 模型：`core` 不应反向依赖 `models`，
否则分层就断了。任何带 `is_superuser` 与 `has_role()` 的对象都适用。
"""

from __future__ import annotations

from typing import Protocol

from app.core.constants import RoleCode


class HasRoles(Protocol):
    is_superuser: bool

    def has_role(self, *codes: str) -> bool: ...


def is_admin(user: HasRoles) -> bool:
    """平台管理员：组织管理、一切实例可见、终止任意流程。"""
    return user.is_superuser or user.has_role(RoleCode.PLATFORM_ADMIN)


def is_designer(user: HasRoles) -> bool:
    """设计者：表单/流程模板的建、发、停。管理员天然拥有该能力。"""
    return is_admin(user) or user.has_role(RoleCode.DESIGNER)
