from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    create_draft,
    delete_file,
    download_file,
    leave_data,
    submit,
    upload_file,
)


def test_attachment_temp_to_instance_permissions(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
    outsider: tuple[ApiClient, dict[str, Any]],
) -> None:
    outsider_client, _ = outsider
    uploaded = upload_file(
        zhangsan_client, filename="e2e-附件.txt", content=b"attachment-body"
    )
    assert uploaded.status_code in (200, 201), uploaded.text
    attachment_id = uploaded.json()["id"]

    own = download_file(zhangsan_client, attachment_id)
    assert own.status_code == 200, own.text
    assert own.content == b"attachment-body"

    # 临时附件：只有上传者/管理员可看
    assert download_file(lisi_client, attachment_id).status_code in (403, 404)
    assert download_file(outsider_client, attachment_id).status_code in (403, 404)
    assert outsider_client.get(f"files/{attachment_id}").status_code in (403, 404)

    data = leave_data(reason="PERM-04 附件绑定")
    draft = create_draft(zhangsan_client, seed["leave_flow"]["id"], data)
    submitted = submit(
        zhangsan_client,
        draft["id"],
        data,
        attachment_ids=[attachment_id],
    )
    assert submitted.status_code == 200, submitted.text

    # 提交后绑定实例：参与者可下载，无关人仍不可
    participant = download_file(lisi_client, attachment_id)
    assert participant.status_code == 200, participant.text
    assert participant.content == b"attachment-body"
    assert download_file(outsider_client, attachment_id).status_code in (403, 404)


def test_upload_rejects_disallowed_extension(zhangsan_client: ApiClient) -> None:
    response = upload_file(
        zhangsan_client,
        filename="e2e.exe",
        content=b"MZ",
        content_type="application/octet-stream",
    )
    assert response.status_code in (400, 415, 422), response.text


def test_delete_temp_attachment(zhangsan_client: ApiClient) -> None:
    uploaded = upload_file(zhangsan_client, filename="e2e-del.txt", content=b"bye")
    assert uploaded.status_code in (200, 201), uploaded.text
    attachment_id = uploaded.json()["id"]

    deleted = delete_file(zhangsan_client, attachment_id)
    assert deleted.status_code == 200, deleted.text
    assert download_file(zhangsan_client, attachment_id).status_code in (403, 404)
