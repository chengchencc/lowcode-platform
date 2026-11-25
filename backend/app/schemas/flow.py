"""流程模板与版本的 API DTO（F2.x）。

`definition` 直接用 `FlowDefinition` 做类型 —— 请求解析阶段就会拒绝
形状不对的定义（未知节点类型、并行组里塞抄送…），
语义问题（审批人没配、条件引用不存在的字段）留到发布校验时拦。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.constants import FlowStatus, FlowVersionStatus
from app.engine.validate import ValidationIssue
from app.schemas.flow_definition import FlowDefinition


class InitiatorScope(BaseModel):
    """发起范围（F2.5）。"""

    type: Literal["all", "role", "dept"] = "all"
    role_ids: list[int] = Field(default_factory=list)
    dept_ids: list[int] = Field(default_factory=list)


class FlowTemplateBrief(BaseModel):
    id: int
    name: str
    code: str | None = None
    category: str | None = None
    status: str = FlowStatus.DRAFT


class FlowTemplateOut(FlowTemplateBrief):
    description: str | None = None
    form_template_id: int
    form_template_name: str | None = None
    initiator_scope: dict[str, Any] = Field(default_factory=dict)
    current_version_id: int | None = None
    current_version_no: int | None = None
    #: 当前版本锁定的表单版本（F2.6）
    locked_form_version_id: int | None = None
    locked_form_version_no: int | None = None
    draft_version_id: int | None = None
    version_count: int = 0
    #: 审批/填写/抄送节点数（不含条件与并行容器本身）
    node_count: int = 0
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FlowTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    form_template_id: int
    code: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    initiator_scope: InitiatorScope | None = None


class FlowTemplateImport(BaseModel):
    """从 JSON 导入流程配置（F2.9）。

    导入结果始终是**草稿**：绑定目标环境里重新选择的表单，定义里的角色/部门/
    用户 id 原样保留（跨环境未必对得上），由用户在设计器里梳理后再发布。
    导出 JSON 里的 `form_name` / `form_code` 仅作参考，导入时忽略。
    """

    name: str | None = Field(default=None, max_length=128)
    code: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    initiator_scope: InitiatorScope | None = None
    form_template_id: int
    definition: FlowDefinition


class FlowTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    initiator_scope: InitiatorScope | None = None


class FlowTemplateStatusRequest(BaseModel):
    status: FlowStatus


# --------------------------------------------------------------------------- 版本


class FlowVersionBrief(BaseModel):
    id: int
    template_id: int
    version_no: int
    status: str = FlowVersionStatus.DRAFT
    remark: str | None = None
    locked_form_version_id: int
    locked_form_version_no: int | None = None
    created_by: int | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None


class FlowVersionOut(FlowVersionBrief):
    definition: FlowDefinition
    validation_report: dict[str, Any] | None = None


class FlowVersionCreate(BaseModel):
    """新建草稿版本。已存在草稿时后端直接复用（幂等）。"""

    from_version_id: int | None = None


class FlowVersionUpdate(BaseModel):
    definition: FlowDefinition
    #: 设计期可以换绑表单版本；发布时会强制锁到表单的当前发布版本
    locked_form_version_id: int | None = None
    remark: str | None = Field(default=None, max_length=255)


class FlowVersionPublishRequest(BaseModel):
    remark: str | None = Field(default=None, max_length=255)


class FlowValidateResult(BaseModel):
    """F2.7 校验结果。

    用 dict 而不是 `ValidationIssue`：后者是引擎里的标准 dataclass，
    作为响应字段类型需要额外配置才能序列化；API 层统一 `to_dict()` 更直白。
    """

    valid: bool
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


def issues_to_result(issues: list[ValidationIssue]) -> FlowValidateResult:
    return FlowValidateResult(
        valid=not any(i.severity == "error" for i in issues),
        errors=[i.to_dict() for i in issues if i.severity == "error"],
        warnings=[i.to_dict() for i in issues if i.severity != "error"],
    )
