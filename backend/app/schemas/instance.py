"""实例与任务的 API DTO（F3.x / F4.x）。

详情页的 `render` 返回结构较宽松（dict），因为它是多种数据的装配结果，
逐个字段建 Pydantic 模型只会增加改一处要动三处的心智负担；
列表类接口仍用明确模型，前端才好复用类型。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.form_schema import FormSchema


class InstanceOut(BaseModel):
    id: int
    code: str
    title: str
    status: str
    round: int
    flow_template_id: int
    flow_template_name: str | None = None
    flow_version_id: int
    form_version_id: int
    initiator_id: int
    initiator_name: str | None = None
    initiator_dept_name: str | None = None
    current_node_keys: list[str] = Field(default_factory=list)
    abnormal: bool = False
    pending_count: int = 0
    done_count: int = 0
    my_pending_count: int = 0
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_action_at: datetime | None = None
    terminated_reason: str | None = None


# --------------------------------------------------------------------------- 发起


class DraftCreate(BaseModel):
    flow_template_id: int
    title: str | None = Field(default=None, max_length=255)
    data: dict[str, Any] = Field(default_factory=dict)


class DraftUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    data: dict[str, Any] = Field(default_factory=dict)


class SubmitRequest(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=2000)
    attachment_ids: list[int] = Field(default_factory=list)
    #: {节点id: [用户id]} —— 「发起人指定审批人」的选择结果
    assignee_picks: dict[str, list[int]] = Field(default_factory=dict)


class TerminateRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=255)


class WithdrawRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=255)


class StartOptionsOut(BaseModel):
    flow_template_id: int
    flow_template_name: str
    flow_version_id: int
    flow_version_no: int
    form_version_id: int
    form_version_no: int
    #: 表单模板最新已发布版本；大于 form_version_no 说明流程还没跟到最新表单
    form_latest_version_no: int | None = None
    schema_data: FormSchema
    #: 发起节点的字段权限 —— 前端据此渲染，不自己推导
    permissions: dict[str, dict[str, Any]]
    #: 规则求值前的权限，前端据此在本地重放联动规则
    base_permissions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    #: 表单联动规则
    form_rules: list[dict[str, Any]] = Field(default_factory=list)
    #: 发起时的系统自动填充值（发起人 / 发起人所在部门）
    auto_fill_values: dict[str, Any] = Field(default_factory=dict)
    #: 需要发起人指定审批人的节点
    initiator_select_nodes: list[dict[str, Any]] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)


# --------------------------------------------------------------------------- 任务


class AssignmentActRequest(BaseModel):
    action: str = Field(pattern="^(AGREE|REJECT|RETURN|SUBMIT)$")
    opinion: str | None = Field(default=None, max_length=2000)
    attachment_ids: list[int] = Field(default_factory=list)
    #: 本节点可编辑字段的修改
    field_patch: dict[str, Any] = Field(default_factory=dict)
    #: 退回时的目标节点 id
    return_target: str | None = None
    #: 客户端乐观锁：与实例当前 version 不符则 409
    expected_version: int | None = None


class TaskRow(BaseModel):
    """待办 / 已办 / 抄送列表的一行。"""

    assignment_id: int
    task_id: int
    user_id: int
    status: str
    result: str | None = None
    seq: int = 0
    is_read: bool = False
    read_at: datetime | None = None
    acted_at: datetime | None = None
    opinion: str | None = None
    node_key: str | None = None
    node_name: str | None = None
    node_type: str | None = None
    assignee_mode: str | None = None
    round: int | None = None
    group_id: str | None = None
    group_member_count: int | None = None
    activated_at: datetime | None = None

    instance_id: int | None = None
    instance_code: str | None = None
    instance_title: str | None = None
    instance_status: str | None = None
    flow_template_id: int | None = None
    flow_template_name: str | None = None
    initiator_id: int | None = None
    initiator_name: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_action_at: datetime | None = None


class TodoSummary(BaseModel):
    todo: int = 0
    cc_unread: int = 0
    mine_running: int = 0


# --------------------------------------------------------------------------- 机制 C


class ExtFieldCreate(BaseModel):
    """运行中追加一个字段（PRD F5.1 / §3.4 机制 C）。"""

    label: str = Field(min_length=1, max_length=64)
    type: str
    required: bool = False
    #: 可编辑的节点 id；不给则由服务端填「当前待办节点」
    editable_node_ids: list[str] = Field(default_factory=list)
    #: 归入哪个分区；不给则落到虚拟分区「扩展字段」
    section_key: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    placeholder: str | None = Field(default=None, max_length=128)


# --------------------------------------------------------------------------- 通知


class NotificationOut(BaseModel):
    # 直接从 ORM 对象构造（字段与模型一一对应，无需手工映射）
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    title: str
    content: str | None = None
    payload: dict[str, Any] | None = None
    link: str | None = None
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationIdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)
