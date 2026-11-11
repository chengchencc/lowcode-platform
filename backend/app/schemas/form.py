"""表单模板与版本的 API DTO（F1.x）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.constants import FormStatus, FormVersionStatus
from app.schemas.form_schema import FormSchema, SchemaIssue


class FormTemplateBrief(BaseModel):
    id: int
    name: str
    code: str | None = None
    group_name: str | None = None
    icon: str | None = None
    status: str = FormStatus.DRAFT


class FormTemplateOut(FormTemplateBrief):
    description: str | None = None
    current_version_id: int | None = None
    current_version_no: int | None = None
    #: 最新一个 DRAFT 版本的 id（有的话），设计器据此决定「继续编辑」还是「新建版本」
    draft_version_id: int | None = None
    version_count: int = 0
    #: schema 里的字段总数（列表页展示用，避免前端拉全量 schema）
    field_count: int = 0
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FormTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    group_name: str | None = Field(default=None, max_length=64)
    icon: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=512)
    #: 新建时可直接带一份初始 schema；不给则自动生成一个「申请信息」分区
    schema_data: FormSchema | None = None


class FormTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    #: 仅允许在尚未设置时补录；已设置的值不可修改（见 form_service.update_template）
    code: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    group_name: str | None = Field(default=None, max_length=64)
    icon: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=512)


class FormTemplateCopy(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    code: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")


class FormTemplateStatusRequest(BaseModel):
    status: FormStatus


# --------------------------------------------------------------------------- 版本


class FormVersionBrief(BaseModel):
    id: int
    template_id: int
    version_no: int
    status: str = FormVersionStatus.DRAFT
    remark: str | None = None
    created_by: int | None = None
    published_at: datetime | None = None
    created_at: datetime | None = None


class FormVersionOut(FormVersionBrief):
    #: 字段名刻意叫 schema_data 而不是 schema —— pydantic v2 里 `schema`
    #: 是 BaseModel 的已废弃方法名，用作字段会触发告警。全链路统一 schema_data。
    schema_data: FormSchema
    #: 该版本被哪些流程版本引用（M3 填充；M2 恒为空）
    referenced_by_flows: list[dict[str, Any]] = Field(default_factory=list)


class FormVersionCreate(BaseModel):
    #: 从哪个版本 fork；不给则从当前版本复制，都没有则给空表单
    from_version_id: int | None = None
    remark: str | None = Field(default=None, max_length=255)


class FormVersionUpdate(BaseModel):
    schema_data: FormSchema
    remark: str | None = Field(default=None, max_length=255)


class FormVersionValidateResult(BaseModel):
    valid: bool
    errors: list[SchemaIssue] = Field(default_factory=list)
    warnings: list[SchemaIssue] = Field(default_factory=list)


class FormVersionPublishRequest(BaseModel):
    remark: str | None = Field(default=None, max_length=255)


class FormPreviewRequest(BaseModel):
    #: 设计器传入的样例数据；不给则用字段默认值兜底
    sample_data: dict[str, Any] = Field(default_factory=dict)


class FormPreviewField(BaseModel):
    key: str
    label: str
    type: str
    computed: Any = None


class FormPreviewOut(BaseModel):
    """设计器预览（F1.4）：把一个版本按指定数据渲染出结构快照。"""

    version_id: int
    template_id: int
    schema_data: FormSchema
    #: 样例数据填充后的值（含公式服务端重算结果）
    sample_data: dict[str, Any] = Field(default_factory=dict)
    computed_fields: list[FormPreviewField] = Field(default_factory=list)


class FormTemplateImport(BaseModel):
    """导入 JSON（F1.8）。结构为导出接口的原样回传。"""

    name: str | None = Field(default=None, max_length=128)
    code: str | None = Field(default=None, max_length=64)
    group_name: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=512)
    schema_data: FormSchema
