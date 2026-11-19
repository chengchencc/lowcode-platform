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
    leave_data,
    parallel_all_definition,
    parallel_any_definition,
    render,
    simple_data,
    submit,
    terminate,
    todo,
    withdraw,
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


def _submit_with(client: ApiClient, flow_id: int, data: dict[str, Any]) -> int:
    draft = create_draft(client, flow_id, data)
    response = submit(client, draft["id"], data)
    assert response.status_code == 200, response.text
    return draft["id"]


def test_concurrent_withdraw_and_approve_has_single_final_state(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_with(
        zhangsan_client,
        seed["leave_flow"]["id"],
        leave_data(reason="CONC-01 撤回vs同意"),
    )
    task = find_assignment(lisi_client, instance_id)
    barrier = threading.Barrier(2)

    def do_withdraw() -> int:
        barrier.wait(timeout=5)
        return withdraw(zhangsan_client, instance_id, reason="并发撤回").status_code

    def do_approve() -> int:
        barrier.wait(timeout=5)
        return act(lisi_client, task["assignment_id"], opinion="并发同意").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = [
            future.result(timeout=20)
            for future in [
                pool.submit(do_withdraw),
                pool.submit(do_approve),
            ]
        ]

    assert 500 not in statuses, f"并发动作不应 500：{statuses}"
    assert 200 in statuses, f"至少一个动作应成功：{statuses}"
    instance = render(zhangsan_client, instance_id).json()["instance"]
    assert instance["status"] in {"WITHDRAWN", "APPROVED"}, instance
    assert [item for item in todo(lisi_client) if item["instance_id"] == instance_id] == []


def test_concurrent_terminate_and_approve_has_single_final_state(
    zhangsan_client: ApiClient,
    lisi_client: ApiClient,
    admin_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    instance_id = _submit_with(
        zhangsan_client,
        seed["leave_flow"]["id"],
        leave_data(reason="CONC-01 终止vs同意"),
    )
    task = find_assignment(lisi_client, instance_id)
    barrier = threading.Barrier(2)

    def do_terminate() -> int:
        barrier.wait(timeout=5)
        return terminate(admin_client, instance_id, reason="并发终止").status_code

    def do_approve() -> int:
        barrier.wait(timeout=5)
        return act(lisi_client, task["assignment_id"], opinion="并发同意").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = [
            future.result(timeout=20)
            for future in [
                pool.submit(do_terminate),
                pool.submit(do_approve),
            ]
        ]

    assert 500 not in statuses, f"并发动作不应 500：{statuses}"
    assert 200 in statuses, f"至少一个动作应成功：{statuses}"
    instance = render(zhangsan_client, instance_id).json()["instance"]
    assert instance["status"] in {"TERMINATED", "APPROVED"}, instance
    assert [item for item in todo(lisi_client) if item["instance_id"] == instance_id] == []


def test_simultaneous_any_sign_has_single_winner(
    admin_client: ApiClient,
    zhangsan_client: ApiClient,
    seed: dict[str, Any],
) -> None:
    form = create_form_and_publish(admin_client, name="E2E 并发或签表单")
    flow = create_flow_and_publish(
        admin_client,
        form_template_id=form["id"],
        name="E2E 并发或签流程",
        definition=parallel_any_definition(
            [seed["users"]["lisi"]["id"], seed["users"]["wangwu"]["id"]]
        ),
    )
    instance_id = _submit_with(
        zhangsan_client, flow["id"], simple_data(reason="CONC-01 并发或签")
    )
    lisi_client = ApiClient.login("lisi", "demo123456")[0]
    wangwu_client = ApiClient.login("wangwu", "demo123456")[0]
    try:
        lisi_task = find_assignment(lisi_client, instance_id)
        wangwu_task = find_assignment(wangwu_client, instance_id)
        barrier = threading.Barrier(2)

        def approve(client: ApiClient, assignment_id: int) -> int:
            barrier.wait(timeout=5)
            return act(client, assignment_id, opinion="并发或签").status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = [
                future.result(timeout=20)
                for future in [
                    pool.submit(approve, lisi_client, lisi_task["assignment_id"]),
                    pool.submit(approve, wangwu_client, wangwu_task["assignment_id"]),
                ]
            ]

        assert 500 not in statuses, f"并发动作不应 500：{statuses}"
        assert 200 in statuses, f"至少一个或签人成功：{statuses}"
        instance = render(zhangsan_client, instance_id).json()["instance"]
        assert instance["status"] == "APPROVED"
        assert [item for item in todo(lisi_client) if item["instance_id"] == instance_id] == []
        assert [item for item in todo(wangwu_client) if item["instance_id"] == instance_id] == []
    finally:
        lisi_client.close()
        wangwu_client.close()
