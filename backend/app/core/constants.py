"""全局枚举与字典。

一律存字符串（决策 D4）：SQLite 没有原生 ENUM，且后续加值不需要改表结构。
"""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class DeptStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class RoleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class RoleCode(StrEnum):
    """内置角色 code。自定义角色由管理员自行命名，不与这些冲突即可。"""

    PLATFORM_ADMIN = "platform_admin"
    DESIGNER = "designer"
    DEPT_MANAGER = "dept_manager"
    FINANCE = "finance"


#: 内置角色定义：(code, 名称, 说明)
BUILTIN_ROLES: tuple[tuple[str, str, str], ...] = (
    (RoleCode.PLATFORM_ADMIN, "平台管理员", "管理组织与全局设置，可终止任意流程、查看全部实例"),
    (RoleCode.DESIGNER, "设计者", "新建/发布/停用表单模板与流程模板"),
    (RoleCode.DEPT_MANAGER, "部门主管", "用于「部门主管」类审批人解析；也可标记为部门负责人"),
    (RoleCode.FINANCE, "财务", "用于财务类审批人解析"),
)


class AuditBizType(StrEnum):
    USER = "USER"
    DEPT = "DEPT"
    ROLE = "ROLE"
    FORM_TEMPLATE = "FORM_TEMPLATE"      # M2
    FLOW_TEMPLATE = "FLOW_TEMPLATE"      # M3
    INSTANCE = "INSTANCE"                # M3+


class AuditAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    PUBLISH = "PUBLISH"
    DISABLE = "DISABLE"
    ENABLE = "ENABLE"
    RESET_PASSWORD = "RESET_PASSWORD"
    IMPORT = "IMPORT"
    GRANT_ROLE = "GRANT_ROLE"
    REVOKE_ROLE = "REVOKE_ROLE"
    TERMINATE = "TERMINATE"
    ADD_EXT_FIELD = "ADD_EXT_FIELD"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"
