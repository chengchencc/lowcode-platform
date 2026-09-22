"""角色管理接口（F6.3）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import AdminUser, ClientIp, CurrentUser, DbSession
from app.schemas.common import MembersRequest, OkResp
from app.schemas.org import DeptMemberOut, RoleCreate, RoleOut, RoleUpdate
from app.services import role_service

router = APIRouter(prefix="/roles", tags=["角色管理"])


@router.get("", response_model=list[RoleOut], summary="角色列表")
def list_roles(
    db: DbSession,
    _: CurrentUser,
    keyword: Annotated[str | None, Query()] = None,
    role_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[RoleOut]:
    return role_service.list_roles(db, keyword=keyword, status=role_status)


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED, summary="新建角色")
def create_role(payload: RoleCreate, db: DbSession, actor: AdminUser, ip: ClientIp) -> RoleOut:
    role = role_service.create(db, payload, actor=actor, ip=ip)
    return role_service.to_out(db, role)


@router.get("/{role_id}", response_model=RoleOut, summary="角色详情")
def get_role(role_id: int, db: DbSession, _: CurrentUser) -> RoleOut:
    return role_service.to_out(db, role_service.get_or_404(db, role_id))


@router.put("/{role_id}", response_model=RoleOut, summary="修改角色")
def update_role(
    role_id: int, payload: RoleUpdate, db: DbSession, actor: AdminUser, ip: ClientIp
) -> RoleOut:
    role = role_service.update(
        db, role_service.get_or_404(db, role_id), payload, actor=actor, ip=ip
    )
    return role_service.to_out(db, role)


@router.delete("/{role_id}", response_model=OkResp, summary="删除角色")
def delete_role(role_id: int, db: DbSession, actor: AdminUser, ip: ClientIp) -> OkResp:
    role_service.delete(db, role_service.get_or_404(db, role_id), actor=actor, ip=ip)
    return OkResp(message="角色已删除")


@router.get("/{role_id}/members", response_model=list[DeptMemberOut], summary="角色成员")
def list_members(role_id: int, db: DbSession, _: CurrentUser) -> list[DeptMemberOut]:
    users = role_service.list_members(db, role_service.get_or_404(db, role_id))
    return [
        DeptMemberOut(
            id=u.id,
            username=u.username,
            real_name=u.real_name,
            position=u.position,
            status=u.status,
        )
        for u in users
    ]


@router.put("/{role_id}/members", response_model=OkResp, summary="设置角色成员（覆盖式）")
def set_members(
    role_id: int, payload: MembersRequest, db: DbSession, actor: AdminUser
) -> OkResp:
    role_service.set_members(
        db, role_service.get_or_404(db, role_id), payload.user_ids, actor=actor
    )
    return OkResp(message="成员已更新")
