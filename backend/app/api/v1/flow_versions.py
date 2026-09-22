"""流程版本接口（F2.2–F2.7）。

设计器的保存 / 校验 / 发布都走这里。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.core.deps import ClientIp, DbSession, DesignerUser
from app.core.errors import NotFoundError
from app.engine.router import allowed_return_targets
from app.engine.types import Cursor
from app.schemas.common import OkResp
from app.schemas.flow import (
    FlowValidateResult,
    FlowVersionOut,
    FlowVersionPublishRequest,
    FlowVersionUpdate,
    issues_to_result,
)
from app.services import flow_service

router = APIRouter(prefix="/flow-versions", tags=["流程版本"])


@router.get("/{version_id}", response_model=FlowVersionOut, summary="版本详情（含定义）")
def get_version(version_id: int, db: DbSession, _: DesignerUser) -> dict:
    version = flow_service.get_version_or_404(db, version_id)
    return flow_service.version_to_out(db, version)


@router.put("/{version_id}", response_model=FlowVersionOut, summary="保存草稿版本")
def update_version(
    version_id: int,
    payload: FlowVersionUpdate,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    version = flow_service.update_version(
        db,
        flow_service.get_version_or_404(db, version_id),
        definition=payload.definition.model_dump(mode="json"),
        locked_form_version_id=payload.locked_form_version_id,
        remark=payload.remark,
        actor=actor,
        ip=ip,
    )
    return flow_service.version_to_out(db, version)


@router.delete("/{version_id}", response_model=OkResp, summary="删除草稿版本")
def delete_version(
    version_id: int, db: DbSession, actor: DesignerUser, ip: ClientIp
) -> OkResp:
    flow_service.delete_version(
        db, flow_service.get_version_or_404(db, version_id), actor=actor, ip=ip
    )
    return OkResp(message="草稿版本已删除")


@router.post(
    "/{version_id}/validate", response_model=FlowValidateResult, summary="校验（F2.7）"
)
def validate_version(version_id: int, db: DbSession, _: DesignerUser) -> FlowValidateResult:
    issues = flow_service.validate_version(
        db, flow_service.get_version_or_404(db, version_id)
    )
    return issues_to_result(issues)


@router.post(
    "/{version_id}/publish", response_model=FlowVersionOut, summary="发布版本（F2.6）"
)
def publish_version(
    version_id: int,
    payload: FlowVersionPublishRequest,
    db: DbSession,
    actor: DesignerUser,
    ip: ClientIp,
) -> dict:
    version = flow_service.publish_version(
        db,
        flow_service.get_version_or_404(db, version_id),
        remark=payload.remark,
        actor=actor,
        ip=ip,
    )
    return flow_service.version_to_out(db, version)


@router.get(
    "/{version_id}/return-targets",
    summary="某节点可退回的目标集合（设计器用）",
)
def return_targets(
    version_id: int,
    db: DbSession,
    _: DesignerUser,
    node_id: Annotated[str, Query(description="节点标识")],
) -> list[dict]:
    """把「退回目标」的合法集合交给设计器，而不是让它在前端重复实现一遍规则。"""
    version = flow_service.get_version_or_404(db, version_id)
    try:
        from app.engine.compile import compile_definition

        compiled = compile_definition(version.definition)
    except Exception as exc:  # noqa: BLE001
        raise NotFoundError(f"流程定义无法编译：{exc}", code="DEFINITION_MALFORMED") from exc

    node = compiled.nodes.get(node_id)
    if node is None:
        raise NotFoundError(f"节点 “{node_id}” 不存在", code="NODE_NOT_FOUND")

    targets = allowed_return_targets(compiled, Cursor(node_id, node.gates))
    return [{"id": t.id, "name": t.name, "type": t.type} for t in targets]
