"""部门管理接口（F6.2）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import AdminUser, ClientIp, CurrentUser, DbSession
from app.schemas.common import MembersRequest, OkResp
from app.schemas.org import DeptBrief, DeptCreate, DeptMemberOut, DeptOut, DeptUpdate
from app.services import dept_service

router = APIRouter(prefix="/departments", tags=["部门管理"])


@router.get("/tree", response_model=list[DeptOut], summary="部门树")
def dept_tree(
    db: DbSession,
    _: CurrentUser,
    include_disabled: Annotated[bool, Query(description="是否含已停用部门")] = True,
) -> list[DeptOut]:
    """登录用户可读 —— 组织选择器、实例详情等页面都需要部门树。"""
    return dept_service.build_tree(db, status=None if include_disabled else "ACTIVE")


@router.get("/options", response_model=list[DeptBrief], summary="部门平铺选项")
def dept_options(db: DbSession, _: CurrentUser) -> list[DeptBrief]:
    return [
        DeptBrief(id=d.id, name=d.name, code=d.code)
        for d in dept_service.list_all(db)
    ]


@router.post("", response_model=DeptOut, status_code=status.HTTP_201_CREATED, summary="新建部门")
def create_dept(
    payload: DeptCreate, db: DbSession, actor: AdminUser, ip: ClientIp
) -> DeptOut:
    dept = dept_service.create(db, payload, actor=actor, ip=ip)
    return dept_service.to_out(db, dept)


@router.get("/{dept_id}", response_model=DeptOut, summary="部门详情")
def get_dept(dept_id: int, db: DbSession, _: CurrentUser) -> DeptOut:
    return dept_service.to_out(db, dept_service.get_or_404(db, dept_id))


@router.put("/{dept_id}", response_model=DeptOut, summary="修改部门")
def update_dept(
    dept_id: int, payload: DeptUpdate, db: DbSession, actor: AdminUser, ip: ClientIp
) -> DeptOut:
    dept = dept_service.update(
        db, dept_service.get_or_404(db, dept_id), payload, actor=actor, ip=ip
    )
    return dept_service.to_out(db, dept)


@router.delete("/{dept_id}", response_model=OkResp, summary="删除部门")
def delete_dept(dept_id: int, db: DbSession, actor: AdminUser, ip: ClientIp) -> OkResp:
    dept_service.delete(db, dept_service.get_or_404(db, dept_id), actor=actor, ip=ip)
    return OkResp(message="部门已删除")


@router.get("/{dept_id}/members", response_model=list[DeptMemberOut], summary="部门成员")
def list_members(dept_id: int, db: DbSession, _: CurrentUser) -> list[DeptMemberOut]:
    return dept_service.list_members(db, dept_service.get_or_404(db, dept_id))


@router.put("/{dept_id}/members", response_model=OkResp, summary="设置部门成员（覆盖式）")
def set_members(
    dept_id: int, payload: MembersRequest, db: DbSession, actor: AdminUser
) -> OkResp:
    dept_service.set_members(
        db, dept_service.get_or_404(db, dept_id), payload.user_ids, actor=actor
    )
    return OkResp(message="成员已更新")
