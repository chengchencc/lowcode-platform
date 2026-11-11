"""附件服务（F4.4 / F1.6）。

文件本体落本地磁盘，DB 只存元数据（PRD §6 attachments 表）。
上传后一律是 TEMP 状态，业务提交时再绑定 —— 避免半途废弃的表单留下孤儿文件。
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AttachmentStatus, AuditAction, AuditBizType, FieldType
from app.core.errors import BadRequestError, NotFoundError, UnprocessableError
from app.models import Attachment, User
from app.services import audit_service
from app.storage import get_storage

#: 图片类扩展名（图片控件上传时校验用）
IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "gif", "bmp", "webp", "svg"})


def _extension_of(filename: str) -> str:
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def get_or_404(db: Session, attachment_id: int) -> Attachment:
    attachment = db.get(Attachment, attachment_id)
    if attachment is None or attachment.status == AttachmentStatus.DELETED:
        raise NotFoundError("附件不存在", code="ATTACHMENT_NOT_FOUND")
    return attachment


def save_upload(
    db: Session,
    *,
    filename: str,
    content: bytes,
    mime_type: str | None,
    uploader: User,
    image_only: bool = False,
) -> Attachment:
    """保存上传的文件并落一条 TEMP 元数据。"""
    if not content:
        raise BadRequestError("上传的文件为空", code="EMPTY_FILE")

    ext = _extension_of(filename)
    if not ext:
        raise BadRequestError("文件缺少扩展名，无法确定类型", code="MISSING_EXTENSION")

    allowed = settings.allowed_extension_set
    if ext not in allowed:
        raise BadRequestError(
            f"不支持的文件类型 .{ext}",
            code="EXTENSION_NOT_ALLOWED",
            extra={"allowed": sorted(allowed)},
        )
    if image_only and ext not in IMAGE_EXTENSIONS:
        raise BadRequestError(
            f"图片控件只接受图片文件，收到 .{ext}",
            code="NOT_AN_IMAGE",
            extra={"allowed": sorted(IMAGE_EXTENSIONS)},
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise BadRequestError(
            f"文件超过 {settings.max_upload_mb}MB 上限",
            code="FILE_TOO_LARGE",
            extra={"max_mb": settings.max_upload_mb, "size": len(content)},
        )

    # 存储名用 uuid，既避免同名覆盖，也杜绝了原始文件名里的路径分隔符
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    now = datetime.now(UTC)
    rel_path = f"{now:%Y}/{now:%m}/{stored_name}"

    get_storage().save(rel_path, content)

    attachment = Attachment(
        biz_type="TEMP",
        biz_id=0,
        file_name=filename[:255],
        stored_name=stored_name,
        rel_path=rel_path,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        uploader_id=uploader.id,
        status=AttachmentStatus.TEMP,
    )
    db.add(attachment)
    db.flush()

    audit_service.record(
        db,
        actor=uploader,
        biz_type=AuditBizType.INSTANCE,
        biz_id=0,
        action=AuditAction.UPLOAD,
        summary=f"上传附件「{attachment.file_name}」",
        detail={"attachment_id": attachment.id, "size": attachment.size_bytes},
    )
    db.commit()
    db.refresh(attachment)
    return attachment


def read_content(db: Session, attachment: Attachment) -> bytes:
    try:
        return get_storage().read(attachment.rel_path)
    except FileNotFoundError as exc:
        # 元数据在但文件没了（被手工清理/磁盘故障）—— 给明确错误而不是 500
        raise NotFoundError(
            "附件文件已丢失，请联系管理员", code="ATTACHMENT_FILE_MISSING"
        ) from exc


def attach_to(
    db: Session,
    attachment_ids: list[int],
    *,
    biz_type: str,
    biz_id: int,
    instance_id: int | None = None,
    field_key: str | None = None,
    actor: User | None = None,
) -> list[Attachment]:
    """把一批 TEMP 附件绑定到业务对象。M4 提交表单/审批动作时会调用。"""
    if not attachment_ids:
        return []

    rows = list(
        db.scalars(select(Attachment).where(Attachment.id.in_(set(attachment_ids)))).all()
    )
    missing = set(attachment_ids) - {a.id for a in rows}
    if missing:
        raise NotFoundError(f"附件不存在：{sorted(missing)}", code="ATTACHMENT_NOT_FOUND")

    for attachment in rows:
        if attachment.status == AttachmentStatus.DELETED:
            raise UnprocessableError(
                f"附件「{attachment.file_name}」已被删除", code="ATTACHMENT_DELETED"
            )
        if attachment.status == AttachmentStatus.BOUND and attachment.biz_id != biz_id:
            raise UnprocessableError(
                f"附件「{attachment.file_name}」已被其他单据引用",
                code="ATTACHMENT_ALREADY_BOUND",
            )
        attachment.status = AttachmentStatus.BOUND
        attachment.biz_type = biz_type
        attachment.biz_id = biz_id
        if instance_id is not None:
            attachment.instance_id = instance_id
        if field_key is not None:
            attachment.field_key = field_key

    db.flush()
    return rows


def _attachment_ids(value: object) -> list[int]:
    if value is None or value == "":
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[int] = []
    for item in items:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def collect_attachment_ids(form_schema, values: dict) -> list[int]:
    """收集表单值里所有附件/图片 id（含子表行内）。"""
    found: set[int] = set()
    for section in form_schema.sections:
        for field in section.fields:
            if field.type in {FieldType.ATTACHMENT, FieldType.IMAGE}:
                found.update(_attachment_ids(values.get(field.key)))
            if field.type is FieldType.SUBTABLE:
                rows = values.get(field.key)
                if not isinstance(rows, list):
                    continue
                file_cols = [
                    col.key for col in (field.columns or [])
                    if col.type in {FieldType.ATTACHMENT, FieldType.IMAGE}
                ]
                for row in rows:
                    if isinstance(row, dict):
                        for key in file_cols:
                            found.update(_attachment_ids(row.get(key)))
    return list(found)


def bind_instance_attachments(
    db: Session,
    instance,
    form_schema,
    values: dict,
    *,
    extra_ids: list[int] | None = None,
) -> None:
    """把表单/意见里的 TEMP 附件绑定到实例，供发起人与审批参与者下载。"""
    ids = collect_attachment_ids(form_schema, values)
    if extra_ids:
        ids.extend(extra_ids)
    if not ids:
        return
    attach_to(
        db,
        list(dict.fromkeys(ids)),
        biz_type="INSTANCE",
        biz_id=instance.id,
        instance_id=instance.id,
    )


def describe(attachment: Attachment) -> dict:
    return {
        "id": attachment.id,
        "file_name": attachment.file_name,
        "size_bytes": attachment.size_bytes,
        "mime_type": attachment.mime_type,
        "is_image": _extension_of(attachment.stored_name) in IMAGE_EXTENSIONS,
        "uploader_id": attachment.uploader_id,
        "created_at": attachment.created_at,
        "url": f"/api/v1/files/{attachment.id}/download",
    }


def delete_upload(
    db: Session, attachment: Attachment, *, actor: User | None = None
) -> None:
    """删除附件：先标记状态，再删文件。

    顺序刻意如此 —— 若文件删除失败，元数据仍指向一个不存在的文件（表现为
    ATTACHMENT_FILE_MISSING），比「文件还在但没人知道它属于谁」更容易排查。
    """
    attachment.status = AttachmentStatus.DELETED
    db.commit()
    get_storage().delete(attachment.rel_path)
