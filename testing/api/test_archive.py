from __future__ import annotations

from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    approve_reimburse,
    archive,
    archive_export,
    create_draft,
    export_instance,
    find_assignment,
    leave_data,
    start_reimburse,
    submit,
)


def _submit_leave(client: ApiClient, flow_id: int, reason: str) -> int:
    data = leave_data(reason=reason)
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def _approved_leave(client: ApiClient, approver: ApiClient, flow_id: int, reason: str) -> int:
    instance_id = _submit_leave(client, flow_id, reason)
    task = find_assignment(approver, instance_id)
    assert act(approver, task["assignment_id"], opinion="通过").status_code == 200
    return instance_id


def _rejected_leave(client: ApiClient, approver: ApiClient, flow_id: int, reason: str) -> int:
    instance_id = _submit_leave(client, flow_id, reason)
    task = find_assignment(approver, instance_id)
    assert (
        act(approver, task["assignment_id"], action="REJECT", opinion="驳回").status_code
        == 200
    )
    return instance_id


def test_archive_only_approved_and_rejects_other_status(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    approved = _approved_leave(
        zhangsan_client, lisi_client, seed["leave_flow"]["id"], "ARCHIVE-01 已通过"
    )
    running = _submit_leave(zhangsan_client, seed["leave_flow"]["id"], "ARCHIVE-01 运行中")
    rejected = _rejected_leave(
        zhangsan_client, lisi_client, seed["leave_flow"]["id"], "ARCHIVE-01 已驳回"
    )

    response = archive(admin_client)
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()["items"]}
    assert approved in ids
    assert running not in ids
    assert rejected not in ids

    # D-05：归档列表只含 APPROVED，非 APPROVED 查询应被拒绝。
    other = archive(admin_client, {"status": "RUNNING"})
    assert other.status_code in (400, 422), other.text

    forbidden = archive(zhangsan_client)
    assert forbidden.status_code in (403, 404), forbidden.text


def test_running_reimburse_export_hides_supplement(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = start_reimburse(
        zhangsan_client, seed["reimburse_flow"]["id"], amount=2500, reason="PERM-02 运行中导出"
    )
    manager_task = find_assignment(lisi_client, instance_id)
    assert act(lisi_client, manager_task["assignment_id"], opinion="同意").status_code == 200

    response = export_instance(zhangsan_client, instance_id)
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8-sig", errors="replace")
    assert "实际核销金额" not in text
    assert "actualAmount" not in text
    assert "invoiceNo" not in text


def test_approved_reimburse_export_contains_supplement_and_escaped_csv(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = approve_reimburse(
        zhangsan=zhangsan_client,
        lisi=lisi_client,
        wangwu=wangwu_client,
        admin=admin_client,
        flow_id=seed["reimburse_flow"]["id"],
        amount=2500,
        invoice="INV-E2E-901",
        reason="=1+1",
    )

    response = export_instance(zhangsan_client, instance_id)
    assert response.status_code == 200, response.text
    text = response.content.decode("utf-8-sig", errors="replace")
    assert "实际核销金额" in text
    assert "INV-E2E-901" in text
    # R3：以 = 开头的单元格必须加单引号，避免 Excel 当公式执行。
    assert "'=1+1" in text


def test_archive_export_bom_and_formula_escape(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    wangwu_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    approve_reimburse(
        zhangsan=zhangsan_client,
        lisi=lisi_client,
        wangwu=wangwu_client,
        admin=admin_client,
        flow_id=seed["reimburse_flow"]["id"],
        amount=2500,
        invoice="INV-E2E-902",
        reason="=2+2",
    )

    response = archive_export(
        admin_client, {"flow_template_id": seed["reimburse_flow"]["id"]}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    text = response.content.decode("utf-8-sig", errors="replace")
    assert "单号" in text and "实际核销金额" in text
    assert "'=2+2" in text

    forbidden = archive_export(zhangsan_client)
    assert forbidden.status_code in (403, 404), forbidden.text

    invalid = archive_export(admin_client, {"status": "RUNNING"})
    assert invalid.status_code == 422, invalid.text
