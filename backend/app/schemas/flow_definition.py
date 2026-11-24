"""流程定义契约（PRD §3.3）。

`FlowVersion.definition` 这列 JSON 的结构由本模块唯一定义，前端
`src/types/flow.ts` 是它的镜像。命名全链路 snake_case（决策 D10）。

结构总览::

    {
      "model_version": 1,
      "history_view": "own_nodes",  // own_nodes | full | start
      "start": {"id": "start", "type": "start", ...},
      "steps": [
        {"id": "s1", "type": "approval",  ...},
        {"id": "s2", "type": "condition", "branches": [{"id": "s2a", "when": {...}, "steps": [...]}]},
        {"id": "s3", "type": "parallel",  "members": [...]},
        {"id": "s4", "type": "fill",      ...},
        {"id": "s5", "type": "cc",        ...}
      ],
      "end": {"id": "end", "type": "end"}
    }

**节点「位置」的表示**（引擎的核心抽象）：
节点 id 本身不足以定位一个令牌 —— 同一个条件分支里的节点，只有连同
「走的是哪条分支」才唯一。因此令牌位置是 `(node_key, gates, round)`，
其中 `gates` 是分支决策链，形如 `("s2:s2a",)`，嵌套分支时累积。

这带来一个关键性质：**祖先判定退化成 gates 的前缀比较**，
于是「退回时该取消哪些令牌」可以写成纯函数，无需遍历图（见 §4.4）。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.conditions import Comparison, Condition, ConditionGroup

#: 条件结构从 conditions.py 复用（表单规则与流程分支同一套契约）
__all__ = ["Comparison", "Condition", "ConditionGroup"]

# --------------------------------------------------------------------------- 枚举


NodeType = Literal["start", "approval", "fill", "parallel", "condition", "cc", "end"]

AssigneeMode = Literal["SINGLE", "SEQUENTIAL", "ALL", "ANY"]

#: 字段权限模式（PRD §3.4 机制 A）
PermMode = Literal["hidden", "readonly", "editable", "editable-required"]

#: 审批人来源（PRD §3.3.2）
AssigneeSourceType = Literal[
    "user",               # 指定人员
    "role",               # 指定角色
    "dept_manager",       # 指定部门 / 表单部门字段 / 发起人所在部门的主管
    "form_user_field",    # 表单里的人员控件当前值
    "form_dept_field",    # 表单里的部门控件的负责人
    "initiator_select",   # 提交时由发起人从候选范围里选
    "prev_node_actors",   # 上一节点的同意者（V1 可选）
]

#: 审批人未命中时的策略
OnEmptyPolicy = Literal["to_admin", "block_publish"]

#: 驳回策略
RejectPolicy = Literal["reject_to_initiator", "reject_forbidden"]

#: 运行中实例里，已办处理人再次打开时的字段可见范围（PRD §3.4 机制 B）
#: own_nodes：本人已办填写/审批节点权限的并集（默认）
#: full：全部字段只读
#: start：仅发起节点视角
HistoryView = Literal["own_nodes", "full", "start"]


# --------------------------------------------------------------------------- 审批人


class AssigneeSource(BaseModel):
    """一条审批人来源规则。多条来源的结果会**合并去重**（PRD §3.3.2「支持组合」）。"""

    type: AssigneeSourceType

    #: type=user
    user_ids: list[int] = Field(default_factory=list)
    #: type=role
    role_ids: list[int] = Field(default_factory=list)
    #: type=dept_manager —— 固定部门（优先于 dept_field）
    dept_ids: list[int] = Field(default_factory=list)
    #: type=dept_manager —— 用表单里哪个部门字段定位部门；不给则用发起人所在部门
    dept_field: str | None = None
    #: type=form_user_field / form_dept_field —— 表单字段 key
    field: str | None = None
    #: type=initiator_select —— 候选人范围
    scope_role_ids: list[int] = Field(default_factory=list)
    scope_dept_ids: list[int] = Field(default_factory=list)
    #: type=prev_node_actors —— 指定看哪个节点（不给则看上一个完成的节点）
    node_id: str | None = None


class AssigneeRule(BaseModel):
    mode: AssigneeMode = "SINGLE"
    sources: list[AssigneeSource] = Field(default_factory=list)
    #: 未命中任何审批人时的行为。默认转平台管理员并标记异常（PRD §3.3.2）
    on_empty: OnEmptyPolicy = "to_admin"
    #: 发起人指定审批人时的候选范围（mode=SINGLE 且含 initiator_select 来源时必填）
    initiator_select: AssigneeSource | None = None

    @model_validator(mode="after")
    def _check_sources(self) -> AssigneeRule:
        has_select = any(s.type == "initiator_select" for s in self.sources)
        if has_select and self.initiator_select is None:
            raise ValueError("包含「发起人指定」来源时，必须给出 initiator_select 候选范围")
        return self


# --------------------------------------------------------------------------- 字段权限


class ConditionalOverride(BaseModel):
    """条件覆盖：满足 `when` 时把某字段设为某个模式。

    实例：`{"when": {"conditions": [{"field": "amount", "cmp": ">", "value": 2000}]},
             "field_key": "amount", "mode": "readonly"}`
    """

    when: ConditionGroup
    field_key: str
    mode: PermMode


class FieldPermissionRule(BaseModel):
    """节点级字段权限矩阵（PRD §3.4 机制 A / 机制 B）。

    求值顺序（后者覆盖前者）见 `engine/permissions.py`：
      L0 节点类型默认 → L1 分区批量(base/partitions) → L2 单字段 → L3 条件覆盖
    """

    #: 未在 partitions 里列出的分区用这个默认值
    base: PermMode = "readonly"
    #: {分区key: 模式} —— 机制 B 的「按分区批量设模板」
    partitions: dict[str, PermMode] = Field(default_factory=dict)
    #: {字段key: 模式} —— 机制 A 的「个别字段覆盖」。子表列写 `items[].amount`
    overrides: dict[str, PermMode] = Field(default_factory=dict)
    #: 条件覆盖，按声明序求值，命中即覆盖
    conditional_overrides: list[ConditionalOverride] = Field(default_factory=list)


# --------------------------------------------------------------------------- 节点


class NodeBase(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    type: NodeType


class ApprovalNode(NodeBase):
    """审批节点：同意 / 驳回 / 退回（PRD §3.3.2）。"""

    type: Literal["approval"] = "approval"
    assignee: AssigneeRule = Field(default_factory=AssigneeRule)
    reject_policy: RejectPolicy = "reject_to_initiator"
    #: 可退回的目标节点 id 白名单。
    #: null = 允许退回全部前序节点；[] = 禁止退回；["s1"] = 仅允许退回 s1
    return_targets: list[str] | None = None
    timeout_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    opinion_required: bool = False
    attachment_required: bool = False
    fields_permission: FieldPermissionRule = Field(default_factory=FieldPermissionRule)


class FillNode(NodeBase):
    """填写节点：只补充填写，无同意/驳回概念（PRD §3.3.2）。"""

    type: Literal["fill"] = "fill"
    assignee: AssigneeRule = Field(default_factory=AssigneeRule)
    return_targets: list[str] | None = None
    timeout_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    fields_permission: FieldPermissionRule = Field(default_factory=FieldPermissionRule)


class ParallelNode(NodeBase):
    """并行组容器：组内成员**同时发起**，聚合模式 all/any（PRD §3.5.3）。

    组内成员只允许 approval / fill（V1 约束，校验器强制）。
    """

    type: Literal["parallel"] = "parallel"
    mode: Literal["all", "any"] = "all"
    members: list[ApprovalNode | FillNode] = Field(default_factory=list)


class Branch(BaseModel):
    """条件分支的一条支路。`when` 为 null 即 else 分支。"""

    id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)
    when: ConditionGroup | None = None
    steps: list[StepNode] = Field(default_factory=list)


class ConditionNode(NodeBase):
    """条件分支节点：按表单值选一条支路；分支走完自动汇合回主线（V1 无通用汇合节点）。"""

    type: Literal["condition"] = "condition"
    branches: list[Branch] = Field(default_factory=list)


class CcNode(NodeBase):
    """抄送节点：只读知会，**不阻塞主线**（PRD §3.3.2）。"""

    type: Literal["cc"] = "cc"
    cc_to: AssigneeRule = Field(default_factory=AssigneeRule)
    #: 被抄送人是否可标记已读
    allow_read: bool = True


StepNode = Annotated[
    ApprovalNode | FillNode | ParallelNode | ConditionNode | CcNode,
    Field(discriminator="type"),
]


class StartNode(NodeBase):
    """发起节点。字段权限即「发起阶段可编辑的字段集合」（PRD §3.4）。

    `fields_permission` **默认为 None**，让 L0 的默认语义生效：

        field.visible_at_start ? editable : hidden

    不能给它一个 `base="hidden"` 的默认规则 —— 那会被当成显式配置去覆盖 L0，
    结果是发起阶段所有字段都不可编辑、提交的数据全被丢弃。
    只有设计者显式配置时才用规则覆盖。
    """

    type: Literal["start"] = "start"
    fields_permission: FieldPermissionRule | None = None


class EndNode(NodeBase):
    type: Literal["end"] = "end"


class FlowDefinition(BaseModel):
    model_version: int = 1
    #: 已办处理人打开运行中实例时的字段范围（详见 HistoryView）。
    #: 终态实例仍按归档视角全量只读，不受此配置影响。
    history_view: HistoryView = "own_nodes"
    start: StartNode = Field(default_factory=lambda: StartNode(id="start", name="发起"))
    steps: list[StepNode] = Field(default_factory=list)
    end: EndNode = Field(default_factory=lambda: EndNode(id="end", name="结束"))


Branch.model_rebuild()
FlowDefinition.model_rebuild()


# --------------------------------------------------------------------------- 便捷访问


def iter_steps(steps: list[StepNode]) -> list[StepNode]:
    """把 steps 拍平成单层（含条件分支与并行组的嵌套成员）。

    用于「按 id 找节点」「统计节点数」这类不关心层级的场景。
    需要层级信息的地方请用 `engine/compile.py` 的 CompiledFlow。
    """
    out: list[StepNode] = []
    for step in steps:
        out.append(step)
        if step.type == "condition":
            for branch in step.branches:
                out.extend(iter_steps(branch.steps))
        elif step.type == "parallel":
            out.extend(step.members)
    return out
