from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from support.client import ApiClient
from support.factories import (
    act,
    create_draft,
    create_flow_and_publish,
    create_form_and_publish,
    find_assignment,
    parallel_all_definition,
    render,
    simple_data,
    submit,
    todo,
)


def test_simultaneous_countersign_both_effects_survive(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 并发会签表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 并发会签流程",
        definition=parallel_all_definition(
            [seed["users"]["lisi"]["id"], seed["users"]["wangwu"]["id"]]
        ),
    )

    data = simple_data(reason="CONC-01 并发会签")
    draft = create_draft(zhangsan_client, flow["id"], data)
    submitted = submit(zhangsan_client, draft["id"], data)
    assert submitted.status_code == 200, submitted.text
    instance_id = draft["id"]

    lisi_client = ApiClient.login("lisi", "demo123456")[0]
    wangwu_client = ApiClient.login("wangwu", "demo123456")[0]
    try:
        lisi_task = find_assignment(lisi_client, instance_id)
        wangwu_task = find_assignment(wangwu_client, instance_id)
        assert lisi_task["group_id"] == wangwu_task["group_id"]

        barrier = threading.Barrier(2)

        def approve(client: ApiClient, assignment_id: int) -> int:
            barrier.wait(timeout=5)
            return act(client, assignment_id, opinion="并发同意").status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(approve, lisi_client, lisi_task["assignment_id"]),
                pool.submit(approve, wangwu_client, wangwu_task["assignment_id"]),
            ]
            statuses = [future.result(timeout=20) for future in futures]

        assert statuses == [200, 200], f"并发会签应全部成功，实际 {statuses}"

        instance = render(zhangsan_client, instance_id).json()["instance"]
        assert instance["status"] == "APPROVED"
        assert instance["done_count"] == 2
        assert [item for item in todo(lisi_client) if item["instance_id"] == instance_id] == []
        assert [item for item in todo(wangwu_client) if item["instance_id"] == instance_id] == []
    finally:
        lisi_client.close()
        wangwu_client.close()
