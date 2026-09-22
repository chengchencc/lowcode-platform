"""表单版本接口（F1.2–F1.6）。

设计器的保存/校验/发布/预览都走这里。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import ClientIp, DbSession, DesignerUser
from app.engine.expressions import evaluate_schema_formulas
from app.schemas.common import OkResp
from app.schemas.form import (
    FormPreviewField,
    FormPreviewOut,
    FormPreviewRequest,
    FormVersionOut,
    FormVersionPublishRequest,
    FormVersionUpdate,
    FormVersionValidateResult,
)
from app.schemas.form_schema import parse_form_schema
from app.services import form_service

router = APIRouter(prefix="/form-versions", tags=["表单版本"])


@router.get("/{version_id}", response_model=FormVersionOut, summary="版本详情（含 schema）")
def get_version(version_id: int, db: DbSession, _: DesignerUser) -> dict:
    version = form_service.get_version_or_404(db, version_id)
    return form_service.version_to_out(db, version)


@router.put("/{version_id}", response_model=FormVersionOut, summary="保存草稿版本")
def update_version(
    version_id: int,
    payload: FormVersionUpdate,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    version = form_service.update_version(
        db, form_service.get_version_or_404(db, version_id), payload, actor=actor, ip=ip
    )
    return form_service.version_to_out(db, version)


@router.delete("/{version_id}", response_model=OkResp, summary="删除草稿版本")
def delete_version(
    version_id: int, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> OkResp:
    form_service.delete_version(
        db, form_service.get_version_or_404(db, version_id), actor=actor, ip=ip
    )
    return OkResp(message="草稿版本已删除")


@router.post(
    "/{version_id}/validate", response_model=FormVersionValidateResult, summary="结构校验（F1.5）"
)
def validate_version(
    version_id: int, db: DbSession, _: DesignerUser
) -> FormVersionValidateResult:
    issues = form_service.validate_version(
        db, form_service.get_version_or_404(db, version_id)
    )
    errors = [i for i in issues if i.severity == "error"]
    return FormVersionValidateResult(
        valid=not errors,
        errors=errors,
        warnings=[i for i in issues if i.severity == "warning"],
    )


@router.post("/{version_id}/publish", response_model=FormVersionOut, summary="发布版本（F1.5）")
def publish_version(
    version_id: int,
    payload: FormVersionPublishRequest,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    version = form_service.publish_version(
        db,
        form_service.get_version_or_404(db, version_id),
        actor=actor,
        remark=payload.remark,
        ip=ip,
    )
    return form_service.version_to_out(db, version)


@router.post("/{version_id}/preview", response_model=FormPreviewOut, summary="预览（F1.4）")
def preview_version(
    version_id: int,
    payload: FormPreviewRequest,
    db: DbSession,
    _: DesignerUser,
) -> dict:
    """按样例数据渲染一次，返回服务端算出的字段值。

    预览走服务端重算（决策 D4），所以设计器里看到的公式结果与提交后一致；
    前端的即时计算只是为了输入时不卡顿。
    """
    version = form_service.get_version_or_404(db, version_id)
    schema = parse_form_schema(version.schema)

    values: dict = dict(payload.sample_data)
    # 未提供样例值时用字段默认值兜底，让预览开箱就有内容
    for section in schema.sections:
        for field in section.fields:
            if field.default_value is not None and field.key not in values:
                values[field.key] = field.default_value

    # 求值失败已在 engine 层被吞成 None，这里不会抛 —— 预览不该因为公式坏掉而 500
    updates = evaluate_schema_formulas(schema, values)

    computed: list[FormPreviewField] = []
    for section in schema.sections:
        for field in section.fields:
            if field.formula is not None:
                computed.append(
                    FormPreviewField(
                        key=field.key,
                        label=field.label,
                        type=field.type.value,
                        computed=updates.get(field.key),
                    )
                )
            for col in field.columns:
                if col.formula is None:
                    continue
                rows = updates.get(field.key) or []
                computed.append(
                    FormPreviewField(
                        key=f"{field.key}[].{col.key}",
                        label=f"{field.label} · {col.label}",
                        type=col.type.value,
                        computed=rows[0].get(col.key) if rows else None,
                    )
                )

    values.update(updates)
    return {
        "version_id": version.id,
        "template_id": version.template_id,
        "schema_data": version.schema,
        "sample_data": values,
        "computed_fields": [c.model_dump() for c in computed],
    }
