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


class WorkStatSheetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class AuditBizType(StrEnum):
    USER = "USER"
    DEPT = "DEPT"
    ROLE = "ROLE"
    FORM_TEMPLATE = "FORM_TEMPLATE"      # M2
    FLOW_TEMPLATE = "FLOW_TEMPLATE"      # M3
    INSTANCE = "INSTANCE"                # M3+
    WORK_STAT_SHEET = "WORK_STAT_SHEET"  # M12
    AI = "AI"                            # M15


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
    COPY = "COPY"
    UPLOAD = "UPLOAD"
    EXPORT = "EXPORT"
    AI_GENERATE = "AI_GENERATE"

#: 审计动作 / 对象的中文名。**前端 `src/stores/app.ts` 是这份映射的镜像**
#: （列表展示用）—— 新增动作时两边都要加，否则界面上会露出英文枚举值。
AUDIT_ACTION_LABELS: dict[str, str] = {
    AuditAction.CREATE: "新建",
    AuditAction.UPDATE: "修改",
    AuditAction.DELETE: "删除",
    AuditAction.ENABLE: "启用",
    AuditAction.DISABLE: "停用",
    AuditAction.RESET_PASSWORD: "重置密码",
    AuditAction.IMPORT: "导入",
    AuditAction.GRANT_ROLE: "授予角色",
    AuditAction.REVOKE_ROLE: "移除角色",
    AuditAction.PUBLISH: "发布",
    AuditAction.TERMINATE: "终止",
    AuditAction.ADD_EXT_FIELD: "追加字段",
    AuditAction.COPY: "复制",
    AuditAction.UPLOAD: "上传",
    AuditAction.EXPORT: "导出",
    AuditAction.AI_GENERATE: "AI 生成",
}

AUDIT_BIZ_LABELS: dict[str, str] = {
    AuditBizType.USER: "用户",
    AuditBizType.DEPT: "部门",
    AuditBizType.ROLE: "角色",
    AuditBizType.FORM_TEMPLATE: "表单模板",
    AuditBizType.FLOW_TEMPLATE: "流程模板",
    AuditBizType.INSTANCE: "流程实例",
    AuditBizType.WORK_STAT_SHEET: "工作量统计",
    AuditBizType.AI: "AI 生成",
}



class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


# --------------------------------------------------------------------------- 表单（M2）


class FormStatus(StrEnum):
    """表单模板主档状态。"""

    DRAFT = "DRAFT"          # 还没有已发布版本
    PUBLISHED = "PUBLISHED"  # 至少有一个已发布版本
    DISABLED = "DISABLED"    # 停用：不可被新流程引用，已有实例不受影响


class FormVersionStatus(StrEnum):
    DRAFT = "DRAFT"          # 编辑中；同一模板同时只允许一个
    PUBLISHED = "PUBLISHED"  # 已发布；被流程版本引用后不可删除
    ARCHIVED = "ARCHIVED"    # 被更新的发布版本取代


class SectionStage(StrEnum):
    """分区阶段标签（PRD §3.2.1）。决定该分区在审批节点上的默认可见性。

    这是「字段累积」机制 B 的基础：申请区在发起时可编辑、后续节点只读；
    补充区默认对所有非目标节点隐藏，由字段权限矩阵显式打开。
    """

    APPLY = "apply"            # 申请区
    APPROVE = "approve"        # 审批区
    SUPPLEMENT = "supplement"  # 补充区（默认隐藏，逐节点揭晓）
    ARCHIVE = "archive"        # 归档区


class FieldType(StrEnum):
    """控件类型（PRD §3.2.2 全量清单）。"""

    # 基础
    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    RADIO = "radio"
    CHECKBOX = "checkbox"
    SELECT = "select"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    SWITCH = "switch"
    # 组织
    USER = "user"
    USER_MULTI = "user_multi"
    DEPT = "dept"
    DEPT_MULTI = "dept_multi"
    # 文件
    ATTACHMENT = "attachment"
    IMAGE = "image"
    # 子表
    SUBTABLE = "subtable"
    # 增强
    FORMULA = "formula"
    CASCADER = "cascader"
    # 展示（不绑定数据，M8）
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    DIVIDER = "divider"
    IMAGE_VIEW = "image_view"
    RICH_TEXT = "rich_text"


#: 需要配置 options 的控件
OPTION_FIELD_TYPES: frozenset[str] = frozenset(
    {FieldType.RADIO, FieldType.CHECKBOX, FieldType.SELECT}
)

#: 值为多选的控件（用 list 存储）
MULTI_VALUE_FIELD_TYPES: frozenset[str] = frozenset(
    {FieldType.CHECKBOX, FieldType.USER_MULTI, FieldType.DEPT_MULTI, FieldType.IMAGE}
)

#: 子表行内允许嵌套的控件（PRD：子表行内嵌基础控件；禁止嵌套子表）
SUBTABLE_COLUMN_TYPES: frozenset[str] = frozenset(
    {
        FieldType.TEXT, FieldType.TEXTAREA, FieldType.NUMBER,
        FieldType.RADIO, FieldType.CHECKBOX, FieldType.SELECT,
        FieldType.DATE, FieldType.TIME, FieldType.DATETIME, FieldType.SWITCH,
        FieldType.USER, FieldType.USER_MULTI, FieldType.DEPT, FieldType.DEPT_MULTI,
        FieldType.ATTACHMENT, FieldType.IMAGE, FieldType.FORMULA,
    }
)

#: 只读控件（由公式计算，用户不可编辑）—— 这些控件类型在权限矩阵里不可配为 editable
COMPUTED_FIELD_TYPES: frozenset[str] = frozenset({FieldType.FORMULA})

#: 展示型控件（M8）：只负责排版与说明，不绑定实例数据。
#: 不进入 current_data / 快照 / CSV / 值校验 / 字段权限矩阵的编辑项。
DISPLAY_FIELD_TYPES: frozenset[str] = frozenset(
    {
        FieldType.HEADING,
        FieldType.PARAGRAPH,
        FieldType.DIVIDER,
        FieldType.IMAGE_VIEW,
        FieldType.RICH_TEXT,
    }
)


class AutoFillSource(StrEnum):
    """发起时自动填充的系统值来源。"""

    INITIATOR = "initiator"            # 当前发起人（user / user_multi）
    INITIATOR_DEPT = "initiator_dept"  # 发起人所在部门（dept / dept_multi）
    START_TIME = "start_time"          # 流程发起时间（datetime）


#: 每种自动填充来源允许的控件类型
AUTO_FILL_FIELD_TYPES: dict[str, frozenset[str]] = {
    AutoFillSource.INITIATOR: frozenset({FieldType.USER, FieldType.USER_MULTI}),
    AutoFillSource.INITIATOR_DEPT: frozenset({FieldType.DEPT, FieldType.DEPT_MULTI}),
    AutoFillSource.START_TIME: frozenset({FieldType.DATETIME}),
}

#: 发起时可带入、但允许发起人修改的默认值来源
DEFAULT_SOURCE_FIELD_TYPES: dict[str, frozenset[str]] = {
    AutoFillSource.INITIATOR: frozenset({FieldType.USER, FieldType.USER_MULTI}),
    AutoFillSource.INITIATOR_DEPT: frozenset({FieldType.DEPT, FieldType.DEPT_MULTI}),
}


class FormulaType(StrEnum):
    """公式基础子集（PRD §10 #9）。"""

    ARITHMETIC = "arithmetic"      # 数字四则：amount * 0.1 + 100
    SUBTABLE_SUM = "subtable_sum"  # 子表某列合计
    DATE_DIFF = "date_diff"        # 日期差（天）
    CONCAT = "concat"              # 文本拼接


#: 公式里允许调用的函数白名单。
#: 必须与 engine/expressions.py 的实现、前端 src/utils/formula.ts、
#: docs/formula-test-vectors.json 三处保持一致。
#: 放在 constants 而非 expressions 里，是为了让 schemas/form_schema.py 的
#: 校验器也能用，同时避免 schemas ↔ engine 的循环导入。
#:
#: ROUND 是对 PRD「纯四则」的一处小扩展 —— 金额计算必须要能控制小数位。
FORMULA_FUNCTIONS: frozenset[str] = frozenset({"ROUND", "ABS", "MIN", "MAX"})

#: 公式表达式里会被当作关键字跳过的标识符（不是字段引用）
FORMULA_KEYWORDS: frozenset[str] = frozenset({"and", "or", "not", "true", "false"})


class AttachmentBizType(StrEnum):
    TEMP = "TEMP"                # 已上传但还没被业务绑定
    FORM_DRAFT = "FORM_DRAFT"    # 表单草稿
    INSTANCE = "INSTANCE"        # 流程实例（M4）


class AttachmentStatus(StrEnum):
    TEMP = "TEMP"
    BOUND = "BOUND"
    DELETED = "DELETED"


# --------------------------------------------------------------------------- 流程（M3）


class FlowStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    DISABLED = "DISABLED"


class FlowVersionStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class InstanceStatus(StrEnum):
    """顶层生命周期状态机（PRD §3.5.1）。用户可感知的业务状态。"""

    DRAFT = "DRAFT"          # 草稿，未提交
    RUNNING = "RUNNING"      # 审批中（含并行多任务、退回节点重派）
    REJECTED = "REJECTED"    # 已驳回，等发起人重填或放弃
    APPROVED = "APPROVED"    # 已通过（归档）
    WITHDRAWN = "WITHDRAWN"  # 已撤回/撤销
    TERMINATED = "TERMINATED"  # 已终止


#: 终态：不能再有任何令牌变化
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {InstanceStatus.APPROVED, InstanceStatus.WITHDRAWN, InstanceStatus.TERMINATED}
)

#: 实例状态的中文名。面向人的输出（错误提示、导出、通知）都从这里取，
#: 免得同一种状态在三个模块里各写一份中文。
INSTANCE_STATUS_LABELS: dict[str, str] = {
    InstanceStatus.DRAFT: "草稿",
    InstanceStatus.RUNNING: "审批中",
    InstanceStatus.REJECTED: "已驳回",
    InstanceStatus.APPROVED: "已通过（归档）",
    InstanceStatus.WITHDRAWN: "已撤回",
    InstanceStatus.TERMINATED: "已终止",
}


class TaskStatus(StrEnum):
    PENDING = "PENDING"        # 活跃令牌
    COMPLETED = "COMPLETED"    # 节点已通过
    CANCELLED = "CANCELLED"    # 被取消（或签他人达成 / 驳回 / 退回 / 撤回 / 终止）


class AssignmentStatus(StrEnum):
    WAITING = "WAITING"      # 依次审批模式下还没轮到的
    PENDING = "PENDING"      # 待办
    DONE = "DONE"            # 已处理
    CANCELLED = "CANCELLED"  # 已取消


class AssignmentResult(StrEnum):
    AGREE = "AGREE"
    REJECT = "REJECT"
    RETURN = "RETURN"
    SUBMIT = "SUBMIT"   # 填写节点
    READ = "READ"       # 抄送已读


class TaskType(StrEnum):
    APPROVAL = "APPROVAL"
    FILL = "FILL"
    CC = "CC"


class AggregateMode(StrEnum):
    """审批人模式（PRD §3.3.2）。"""

    SINGLE = "SINGLE"          # 单人
    SEQUENTIAL = "SEQUENTIAL"  # 多人依次
    ALL = "ALL"                # 并行会签：全部同意才通过
    ANY = "ANY"                # 并行或签：任一同意即通过


class CancelReason(StrEnum):
    ANY_SIGN_DONE = "ANY_SIGN_DONE"    # 或签他人已处理
    TRANSFERRED = "TRANSFERRED"        # 转办（M14）
    REJECTED = "REJECTED"
    RETURNED = "RETURNED"
    WITHDRAWN = "WITHDRAWN"
    TERMINATED = "TERMINATED"
    RESUBMITTED = "RESUBMITTED"
    GROUP_FAILED = "GROUP_FAILED"


class DelegationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class SnapshotKind(StrEnum):
    SUBMIT = "SUBMIT"
    ACTION = "ACTION"
    RETURN = "RETURN"
    REJECT = "REJECT"
    EXT_FIELD = "EXT_FIELD"
    TERMINATE = "TERMINATE"
    ARCHIVE = "ARCHIVE"


class NotifType(StrEnum):
    TASK_CREATED = "TASK_CREATED"
    TASK_CANCELLED = "TASK_CANCELLED"
    INSTANCE_APPROVED = "INSTANCE_APPROVED"
    INSTANCE_REJECTED = "INSTANCE_REJECTED"
    INSTANCE_RETURNED = "INSTANCE_RETURNED"
    INSTANCE_WITHDRAWN = "INSTANCE_WITHDRAWN"
    INSTANCE_TERMINATED = "INSTANCE_TERMINATED"
    CC_RECEIVED = "CC_RECEIVED"
    ABNORMAL_ASSIGN = "ABNORMAL_ASSIGN"
    EXT_FIELD_ADDED = "EXT_FIELD_ADDED"
    TASK_TRANSFERRED = "TASK_TRANSFERRED"
    TASK_DELEGATED = "TASK_DELEGATED"
