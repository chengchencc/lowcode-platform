"""处理历史时间线（F4.6 / PRD §3.6）。

按时间正序给出每个动作：谁、在哪个节点、做了什么、意见、字段改了什么、
以及**当时的快照 id**（可点进去看那个时点的完整表单）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Attachment, FlowInstance, InstanceAction, User
from app.services import snapshot_service

#: 动作 → 中文标签
ACTION_LABELS: dict[str, str] = {
    "SUBMIT": "提交",
    "RESUBMIT": "重新提交",
    "AGREE": "同意",
    "REJECT": "驳回",
    "RETURN": "退回",
    "WITHDRAW": "撤回",
    "ABANDON": "撤销",
    "TERMINATE": "终止",
    "CC_READ": "已读抄送",
    "ADD_EXT_FIELD": "追加字段",
    "DISABLE_EXT_FIELD": "停用字段",
}


def action_label(action: str) -> str:
    return ACTION_LABELS.get(action, action)


def list_actions(db: Session, instance: FlowInstance) -> list[dict[str, Any]]:
    """该实例的全部动作，**按时间正序**（时间线从上往下读）。"""
    rows = list(
        db.scalars(
            select(InstanceAction)
            .where(InstanceAction.instance_id == instance.id)
            .order_by(InstanceAction.id)
        ).all()
    )
    if not rows:
        return []

    names = _user_names(db, {r.actor_id for r in rows})
    snapshots = {
        s.id: s
        for s in snapshot_service.list_for_instance(db, instance.id)
    }
    attachment_ids = {
        aid for row in rows for aid in (row.attachments or [])
    }
    attachment_names = _attachment_names(db, attachment_ids)

    out: list[dict[str, Any]] = []
    for row in rows:
        snapshot = snapshots.get(row.snapshot_id) if row.snapshot_id else None
        out.append({
            "action_id": row.id,
            "action": row.action,
            "action_label": action_label(row.action),
            "node_key": row.node_key,
            "node_name": row.node_name,
            "actor_id": row.actor_id,
            "actor_name": names.get(row.actor_id, f"#{row.actor_id}"),
            "opinion": row.opinion,
            "round": row.round,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "changed_fields": row.changed_fields or [],
            "attachments": [
                {"id": aid, "file_name": attachment_names.get(aid, f"#{aid}")}
                for aid in (row.attachments or [])
            ],
            "snapshot_id": row.snapshot_id,
            # 快照序号用于展示「第 N 个版本」
            "snapshot_seq": snapshot.seq if snapshot else None,
            "created_at": row.created_at,
        })
    return out


def _user_names(db: Session, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = db.execute(select(User.id, User.real_name).where(User.id.in_(user_ids))).all()
    return {uid: name for uid, name in rows}


def _attachment_names(db: Session, attachment_ids: set[int]) -> dict[int, str]:
    if not attachment_ids:
        return {}
    rows = db.execute(
        select(Attachment.id, Attachment.file_name).where(Attachment.id.in_(attachment_ids))
    ).all()
    return {aid: name for aid, name in rows}
