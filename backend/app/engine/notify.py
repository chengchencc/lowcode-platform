"""通知草稿的构造（PRD F7.1）。

纯函数：只产出 `NotificationDraft`，落库由 service 层完成。

**幂等**：每条草稿都带 `dedup_key`，service 层把它落到
`notifications.dedup_key` 的唯一索引上 —— 引擎的事务重试不会产生重复消息。
这也是为什么 dedup_key 里要带上足够多的区分信息（任务 id、用户 id、事件类型）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from app.core.constants import NotifType
from app.engine.types import NotificationDraft


def _link(instance_id: int, assignment_id: int | None = None) -> str:
    base = f"/instance/{instance_id}"
    return f"{base}?assignment={assignment_id}" if assignment_id else base


def task_created(
    *,
    instance_id: int,
    instance_title: str,
    node_name: str,
    assignments: Iterable[tuple[int, int]],   # (user_id, assignment_id)
    round_no: int = 1,
) -> list[NotificationDraft]:
    """新待办。`assignments` 是 (用户id, assignment id) 列表。"""
    out: list[NotificationDraft] = []
    for user_id, assignment_id in assignments:
        out.append(
            NotificationDraft(
                user_id=user_id,
                type=NotifType.TASK_CREATED,
                title=f"待办：{instance_title}",
                content=f"「{node_name}」等待你处理",
                link=_link(instance_id, assignment_id),
                dedup_key=f"TASK:{assignment_id}:U:{user_id}",
                payload={
                    "instance_id": instance_id,
                    "assignment_id": assignment_id,
                    "node_name": node_name,
                    "round": round_no,
                },
            )
        )
    return out


def task_cancelled(
    *,
    instance_id: int,
    instance_title: str,
    node_name: str,
    assignment_ids: Iterable[tuple[int, int]],  # (user_id, assignment_id)
    reason: str,
) -> list[NotificationDraft]:
    """待办被取消（或签他人达成 / 驳回 / 退回 / 撤回 / 终止）。

    PRD F4.5：相关人员收到知会并在待办移除。
    """
    out: list[NotificationDraft] = []
    for user_id, assignment_id in assignment_ids:
        out.append(
            NotificationDraft(
                user_id=user_id,
                type=NotifType.TASK_CANCELLED,
                title=f"无需处理：{instance_title}",
                content=f"「{node_name}」的待办已取消（{reason}）",
                link=_link(instance_id),
                dedup_key=f"CANCEL:{assignment_id}:U:{user_id}",
                payload={"instance_id": instance_id, "assignment_id": assignment_id},
            )
        )
    return out


def instance_status_changed(
    *,
    instance_id: int,
    instance_title: str,
    status: str,
    recipients: Sequence[int],
    node_name: str | None = None,
    extra: str | None = None,
) -> list[NotificationDraft]:
    """实例级状态变化通知发起人与相关人。"""
    type_map = {
        "APPROVED": (NotifType.INSTANCE_APPROVED, "已通过"),
        "REJECTED": (NotifType.INSTANCE_REJECTED, "被驳回"),
        "WITHDRAWN": (NotifType.INSTANCE_WITHDRAWN, "已撤回"),
        "TERMINATED": (NotifType.INSTANCE_TERMINATED, "已终止"),
    }
    entry = type_map.get(status)
    if entry is None:
        return []
    notif_type, label = entry

    out: list[NotificationDraft] = []
    for user_id in dict.fromkeys(recipients):
        out.append(
            NotificationDraft(
                user_id=user_id,
                type=notif_type,
                title=f"{label}：{instance_title}",
                content=extra,
                link=_link(instance_id),
                dedup_key=f"STATUS:{instance_id}:{status}:U:{user_id}",
                payload={"instance_id": instance_id, "status": status, "node_name": node_name},
            )
        )
    return out


def cc_received(
    *,
    instance_id: int,
    instance_title: str,
    node_name: str,
    assignments: Iterable[tuple[int, int]],
) -> list[NotificationDraft]:
    out: list[NotificationDraft] = []
    for user_id, assignment_id in assignments:
        out.append(
            NotificationDraft(
                user_id=user_id,
                type=NotifType.CC_RECEIVED,
                title=f"抄送给你：{instance_title}",
                content=f"「{node_name}」知会你",
                link=_link(instance_id, assignment_id),
                dedup_key=f"CC:{assignment_id}:U:{user_id}",
                payload={"instance_id": instance_id, "assignment_id": assignment_id},
            )
        )
    return out


def returned(
    *,
    instance_id: int,
    instance_title: str,
    from_node: str,
    to_node: str,
    recipients: Sequence[int],
) -> list[NotificationDraft]:
    out: list[NotificationDraft] = []
    for user_id in dict.fromkeys(recipients):
        out.append(
            NotificationDraft(
                user_id=user_id,
                type=NotifType.INSTANCE_RETURNED,
                title=f"被退回：{instance_title}",
                content=f"「{from_node}」退回到「{to_node}」",
                link=_link(instance_id),
                dedup_key=f"RETURN:{instance_id}:{from_node}:{to_node}:U:{user_id}",
                payload={"instance_id": instance_id, "from": from_node, "to": to_node},
            )
        )
    return out


def ext_field_added(
    *,
    instance_id: int,
    instance_title: str,
    field_key: str,
    label: str,
    node_name: str | None,
    recipients: Sequence[int],
) -> list[NotificationDraft]:
    """运行中追加了字段（机制 C）—— 当前处理人需要知道要多填一个。"""
    out: list[NotificationDraft] = []
    where = f"「{node_name}」" if node_name else "本节点"
    for user_id in dict.fromkeys(recipients):
        out.append(
            NotificationDraft(
                user_id=user_id,
                type=NotifType.EXT_FIELD_ADDED,
                title=f"新增字段：{instance_title}",
                content=f"{where}新增了「{label}」，请一并填写",
                link=_link(instance_id),
                # field_key 才有唯一性 —— 同一个实例上追加两个**同名字段**也要各通知一次
                dedup_key=f"EXT:{instance_id}:{field_key}:U:{user_id}",
                payload={
                    "instance_id": instance_id,
                    "field_key": field_key,
                    "label": label,
                    "node_name": node_name,
                },
            )
        )
    return out


def abnormal_assignment(
    *,
    instance_id: int,
    instance_title: str,
    node_name: str,
    admin_ids: Sequence[int],
    reason: str,
) -> list[NotificationDraft]:
    """审批人未命中 → 通知管理员（PRD §3.3.2，不静默通过）。"""
    out: list[NotificationDraft] = []
    for user_id in dict.fromkeys(admin_ids):
        out.append(
            NotificationDraft(
                user_id=user_id,
                type=NotifType.ABNORMAL_ASSIGN,
                title=f"审批人解析异常：{instance_title}",
                content=f"「{node_name}」{reason}，已转交给你处理",
                link=_link(instance_id),
                dedup_key=f"ABNORMAL:{instance_id}:{node_name}:U:{user_id}",
                payload={"instance_id": instance_id, "node_name": node_name, "reason": reason},
            )
        )
    return out
