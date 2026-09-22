"""数据快照的读取与对照（F4.6 / PRD §3.6）。

快照存的是 `{values, ext_fields}`；模板 schema 由不可变的 `form_versions` 提供，
渲染历史时点只要「那份 schema + 这份值」就能完整还原。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.snapshot import diff_snapshots
from app.models import DataSnapshot

__all__ = ["DataSnapshot", "compare", "list_for_instance", "to_out"]


def list_for_instance(db: Session, instance_id: int) -> list[DataSnapshot]:
    return list(
        db.scalars(
            select(DataSnapshot)
            .where(DataSnapshot.instance_id == instance_id)
            .order_by(DataSnapshot.round, DataSnapshot.seq)
        ).all()
    )


def to_out(db: Session, snapshot: DataSnapshot) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "instance_id": snapshot.instance_id,
        "round": snapshot.round,
        "seq": snapshot.seq,
        "kind": snapshot.kind,
        "created_by": snapshot.created_by,
        "created_at": snapshot.created_at,
        "data_hash": snapshot.data_hash,
    }


def compare(db: Session, left_id: int, right_id: int) -> list[dict[str, Any]]:
    """两个快照之间的字段差异（旧值 → 新值）。"""
    left = db.get(DataSnapshot, left_id)
    right = db.get(DataSnapshot, right_id)
    if left is None or right is None:
        return []
    return diff_snapshots(
        left.data.get("values", {}),
        right.data.get("values", {}),
    )
