"""附件元数据（PRD §6 / F4.4）。

文件本体落本地磁盘（决策：PRD §10 #4），DB 只存相对路径与元数据。
换对象存储时只需替换 `app/storage/` 的实现，本表结构不变。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import AttachmentBizType, AttachmentStatus
from app.db.base import Base, IntType, PkMixin, TimestampMixin


class Attachment(Base, PkMixin, TimestampMixin):
    __tablename__ = "attachments"

    #: 业务归属。上传时一律 TEMP，业务提交时再绑定（避免半途废弃的实例留下孤儿文件）
    biz_type: Mapped[str] = mapped_column(
        String(24), nullable=False, default=AttachmentBizType.TEMP, index=True
    )
    biz_id: Mapped[int] = mapped_column(IntType, nullable=False, default=0, index=True)

    #: 所属流程实例（M3 起才有值）。不建外键：flow_instances 表在 M3 才创建
    instance_id: Mapped[int | None] = mapped_column(IntType, nullable=True, index=True)
    #: 归属字段 key（附件/图片控件、子表单元格）
    field_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: uuid 化的存储名，防止同名覆盖与路径穿越
    stored_name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    #: 相对 STORAGE_ROOT 的路径，如 2026/09/xxxx.pdf
    rel_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    uploader_id: Mapped[int] = mapped_column(
        IntType, ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AttachmentStatus.TEMP, index=True
    )
