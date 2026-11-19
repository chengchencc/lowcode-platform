"""附件上传下载（F4.4 / F1.6）。

表单的附件与图片控件、审批意见的附件都走这里。
上传后是 TEMP 状态，业务提交时由 `file_service.attach_to()` 绑定。
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import Response

from app.core.deps import CurrentUser, DbSession
from app.core.errors import ForbiddenError
from app.core.policy import is_admin
from app.models import FlowInstance
from app.schemas.common import OkResp
from app.services import file_service, instance_service

router = APIRouter(prefix="/files", tags=["附件"])


@router.post("/upload", summary="上传附件")
def upload(
    db: DbSession,
    user: CurrentUser,
    file: Annotated[UploadFile, File(description="要上传的文件")],
    image_only: Annotated[bool, Query(description="图片控件上传时置 true")] = False,
) -> dict:
    attachment = file_service.save_upload(
        db,
        filename=file.filename or "unnamed",
        content=file.file.read(),
        mime_type=file.content_type,
        uploader=user,
        image_only=image_only,
    )
    return file_service.describe(attachment)


def _assert_can_access(db, attachment, user) -> None:
    """可见性：上传者、管理员，或能查看该附件所属实例的参与者。"""
    if attachment.uploader_id == user.id or is_admin(user):
        return
    if attachment.instance_id is not None:
        instance = db.get(FlowInstance, attachment.instance_id)
        if instance is not None and instance_service.can_view(db, instance, user):
            # D-04：附件挂在 hidden 字段上时，即使能查看实例也不能下载。
            if attachment.field_key:
                from app.services import render_service

                rendered = render_service.render_instance(db, instance, viewer=user)
                visible = rendered.get("permissions", {}).get(
                    attachment.field_key, {}
                ).get("visible", False)
                if not visible:
                    raise ForbiddenError(
                        "没有权限访问该附件", code="ATTACHMENT_FORBIDDEN"
                    )
            return
    raise ForbiddenError("没有权限访问该附件", code="ATTACHMENT_FORBIDDEN")


@router.get("/{attachment_id}", summary="附件元数据")
def info(attachment_id: int, db: DbSession, user: CurrentUser) -> dict:
    attachment = file_service.get_or_404(db, attachment_id)
    _assert_can_access(db, attachment, user)
    return file_service.describe(attachment)


@router.get("/{attachment_id}/download", summary="下载附件")
def download(attachment_id: int, db: DbSession, user: CurrentUser) -> Response:
    attachment = file_service.get_or_404(db, attachment_id)
    _assert_can_access(db, attachment, user)
    content = file_service.read_content(db, attachment)
    # 中文文件名要用 RFC 5987 的 filename*，否则浏览器会拿到乱码
    encoded = quote(attachment.file_name)
    return Response(
        content=content,
        media_type=attachment.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{encoded}\"; filename*=UTF-8''{encoded}"
            ),
            "Content-Length": str(len(content)),
        },
    )


@router.delete("/{attachment_id}", response_model=OkResp, summary="删除附件")
def delete_attachment(
    attachment_id: int, db: DbSession, user: CurrentUser
) -> OkResp:
    attachment = file_service.get_or_404(db, attachment_id)
    if attachment.uploader_id != user.id and not is_admin(user):
        raise ForbiddenError("没有权限删除该附件", code="ATTACHMENT_FORBIDDEN")

    file_service.delete_upload(db, attachment, actor=user)
    return OkResp(message="附件已删除")
