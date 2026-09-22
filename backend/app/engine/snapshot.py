"""实例快照的构造与哈希（PRD §3.6）。

快照只存 `{values, ext_fields}`，**不复制模板 schema** ——
`form_versions.schema` 本身不可变（发布后冻结），
渲染历史时点只要「那份 schema + 这份值」就能完整还原。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def build_snapshot_payload(
    values: Mapping[str, Any],
    ext_fields: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """快照的 data 列。

    `ext_fields` 是机制 C 的动态字段**定义**快照 —— 字段定义可能被停用，
    但历史快照要能按当时的定义还原，所以一并存。
    """
    return {
        "values": dict(values),
        "ext_fields": [dict(f) for f in (ext_fields or ())],
    }


def hash_values(values: Mapping[str, Any]) -> str:
    """值内容的 sha256。用于比对与去重（不含 ext_fields，那部分是定义）。"""
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def diff_snapshots(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """两个快照之间的字段差异（PRD F4.6「字段变更对照（旧值→新值）」）。"""
    out: list[dict[str, Any]] = []
    for key in sorted(set(before) | set(after)):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        out.append({"key": key, "old": old, "new": new})
    return out
