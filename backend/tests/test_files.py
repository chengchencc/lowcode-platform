"""附件上传下载测试（F1.6 / F4.4）。"""

from __future__ import annotations

import re

from app.core.constants import AttachmentBizType, AttachmentStatus
from app.models import Attachment
from app.schemas.form_schema import parse_form_schema
from app.services import file_service
from tests.conftest import make_user

BASE = "/api/v1"

# 最小合法 PNG（1x1 像素）
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _upload(client, headers, *, filename="说明.txt", content=b"hello", **params):
    return client.post(
        f"{BASE}/files/upload",
        headers=headers,
        files={"file": (filename, content, "application/octet-stream")},
        params=params,
    )


def test_upload_and_download(client, normal_headers):
    resp = _upload(client, normal_headers, filename="合同.pdf", content=b"pdf-bytes")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["file_name"] == "合同.pdf"
    assert body["size_bytes"] == len(b"pdf-bytes")
    assert body["is_image"] is False
    assert body["url"] == f"/api/v1/files/{body['id']}/download"

    download = client.get(body["url"], headers=normal_headers)
    assert download.status_code == 200
    assert download.content == b"pdf-bytes"
    # 中文文件名不能变成乱码
    assert "filename*=UTF-8''" in download.headers["content-disposition"]


def test_upload_missing_requires_login(client):
    assert _upload(client, {}).status_code == 401


def test_rejects_disallowed_extension(client, normal_headers):
    resp = _upload(client, normal_headers, filename="木马.exe", content=b"MZ")
    assert resp.status_code == 400
    body = resp.json()["detail"]
    assert body["code"] == "EXTENSION_NOT_ALLOWED"
    assert "exe" not in body["extra"]["allowed"]


def test_rejects_missing_extension(client, normal_headers):
    resp = _upload(client, normal_headers, filename="README", content=b"x")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "MISSING_EXTENSION"


def test_rejects_empty_file(client, normal_headers):
    resp = _upload(client, normal_headers, content=b"")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "EMPTY_FILE"


def test_rejects_oversized_file(client, normal_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_upload_mb", 0)  # 让任何非空文件都超限
    resp = _upload(client, normal_headers, content=b"x")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_image_only_rejects_non_image(client, normal_headers):
    resp = _upload(client, normal_headers, filename="a.txt", image_only=True)
    assert resp.status_code == 400
    body = resp.json()["detail"]
    assert body["code"] == "NOT_AN_IMAGE"


def test_image_only_accepts_image(client, normal_headers):
    resp = _upload(client, normal_headers, filename="图.png", content=PNG_BYTES, image_only=True)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_image"] is True


def test_download_forbidden_for_other_user(client, db, normal_headers, designer_role):
    """他人上传的附件，非管理员不能下载（M4 会叠加实例参与者可见性）。"""
    attachment = _upload(client, normal_headers).json()

    other = make_user(db, username="other", password="other123456")
    from tests.conftest import login_as

    other_headers = login_as(client, other.username, "other123456")

    resp = client.get(attachment["url"], headers=other_headers)
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "ATTACHMENT_FORBIDDEN"


def test_admin_can_download_any(client, admin_headers, normal_headers):
    attachment = _upload(client, normal_headers).json()
    assert client.get(attachment["url"], headers=admin_headers).status_code == 200


def test_delete_attachment(client, normal_headers):
    attachment = _upload(client, normal_headers).json()

    assert client.delete(
        f"{BASE}/files/{attachment['id']}", headers=normal_headers
    ).status_code == 200
    # 标记为 DELETED 后即不可访问
    assert client.get(attachment["url"], headers=normal_headers).status_code == 404


def test_bind_form_attachments_to_instance(db):
    """提交后附件要从 TEMP 绑定到实例，审批参与者才能下载。"""
    user = make_user(db, username="attach-owner")
    attachment = Attachment(
        file_name="需求说明书.txt",
        stored_name="bind-test.txt",
        rel_path="test/bind-test.txt",
        size_bytes=1,
        uploader_id=user.id,
        status=AttachmentStatus.TEMP,
        biz_type=AttachmentBizType.TEMP,
    )
    db.add(attachment)
    db.flush()

    schema = parse_form_schema({
        "sections": [{
            "key": "sec", "title": "申请", "fields": [
                {"key": "files", "label": "附件", "type": "attachment"},
            ],
        }],
    })

    class Instance:
        id = 99

    file_service.bind_instance_attachments(db, Instance(), schema, {"files": [attachment.id]})
    db.flush()

    assert attachment.status == AttachmentStatus.BOUND
    assert attachment.instance_id == 99
    assert attachment.biz_type == AttachmentBizType.INSTANCE
    assert attachment.biz_id == 99


def test_collect_attachment_ids_from_subtable(db):
    schema = parse_form_schema({
        "sections": [{
            "key": "sec", "title": "申请", "fields": [
                {"key": "files", "label": "附件", "type": "attachment"},
                {
                    "key": "rows", "label": "明细", "type": "subtable",
                    "columns": [
                        {"key": "doc", "label": "文档", "type": "attachment"},
                    ],
                },
            ],
        }],
    })
    ids = file_service.collect_attachment_ids(
        schema,
        {"files": [1, 2], "rows": [{"doc": [3]}, {"doc": 4}]},
    )
    assert sorted(ids) == [1, 2, 3, 4]


def test_upload_writes_file_to_storage(client, db, normal_headers):
    """元数据落库、文件本体落盘，两者都要对得上。

    注意用测试的 `db` fixture 而不是 `app.db.session.SessionLocal` ——
    后者指向真实的开发库，测试数据在那里不存在。
    """
    from app.core.config import settings
    from app.models import Attachment
    from app.storage import get_storage

    attachment = _upload(client, normal_headers, filename="a.txt", content=b"body").json()

    row = db.get(Attachment, attachment["id"])
    assert row is not None
    assert row.status == "TEMP"
    assert row.sha256 is not None
    # 存储名是 uuid + 原扩展名，不沿用原始文件名（防路径穿越与同名覆盖）。
    # 不能用 `"a.txt" not in stored_name`：uuid 恰好以 a 结尾时，
    # `<uuid>.txt` 的尾部就是 "a.txt"，会随机误报。
    assert re.fullmatch(r"[0-9a-f]{32}\.txt", row.stored_name)
    assert (settings.storage_path / row.rel_path).is_file()
    assert get_storage().read(row.rel_path) == b"body"
