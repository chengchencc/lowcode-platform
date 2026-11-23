"""按查看者可见权限裁剪响应（D-04）。

运行中：hidden 字段的 key、标签、值、子表列、规则引用都不下发；
终态归档：permissions 已是全量 visible + readonly，因此过滤后自然保留全部。

只做“去掉不可见”，不改变可见字段的权限与值。
"""

from __future__ import annotations

import copy
import json
from typing import Any

PermissionMap = dict[str, dict[str, Any]]


def _is_hidden(key: str, permissions: PermissionMap) -> bool:
    permission = permissions.get(key)
    return permission is not None and not permission.get("visible", False)


def _keep(key: str, permissions: PermissionMap) -> bool:
    return not _is_hidden(key, permissions)


def filter_schema(schema: dict[str, Any], permissions: PermissionMap) -> dict[str, Any]:
    """去掉 hidden 字段/子表列；整段都 hidden 的分区一并去掉。"""
    result = copy.deepcopy(schema)
    sections: list[dict[str, Any]] = []
    for section in result.get("sections", []) or []:
        fields: list[dict[str, Any]] = []
        for field in section.get("fields", []) or []:
            key = field.get("key")
            if not key or not _keep(key, permissions):
                continue
            columns = field.get("columns") or []
            if columns:
                visible_columns = [
                    column
                    for column in columns
                    if _keep(f"{key}[].{column.get('key')}", permissions)
                ]
                if not visible_columns:
                    continue
                field["columns"] = visible_columns
            fields.append(field)
        if fields:
            section["fields"] = fields
            sections.append(section)
    result["sections"] = sections
    return result


def filter_permissions(permissions: PermissionMap) -> PermissionMap:
    return {key: value for key, value in permissions.items() if value.get("visible", False)}


def filter_values(values: dict[str, Any], permissions: PermissionMap) -> dict[str, Any]:
    """去掉 hidden 字段值；子表行只保留可见列。"""
    result: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if not _keep(key, permissions):
            continue
        column_keys = {
            permission_key.split("].", 1)[1]
            for permission_key in permissions
            if permission_key.startswith(f"{key}[].")
        }
        if column_keys and isinstance(value, list):
            value = [
                {k: v for k, v in row.items() if _keep(f"{key}[].{k}", permissions)}
                if isinstance(row, dict)
                else row
                for row in value
            ]
        result[key] = value
    return result


def _rule_uses_hidden(rule: Any, hidden_keys: set[str]) -> bool:
    text = json.dumps(rule, ensure_ascii=False)
    return any(f'"{key}"' in text for key in hidden_keys)


def filter_rules(rules: list[Any], permissions: PermissionMap) -> list[Any]:
    hidden_keys = {key for key in permissions if _is_hidden(key, permissions)}
    if not hidden_keys:
        return rules
    return [rule for rule in rules if not _rule_uses_hidden(rule, hidden_keys)]


def filter_actions(
    actions: list[dict[str, Any]], permissions: PermissionMap
) -> list[dict[str, Any]]:
    """时间线动作里的字段 diff 只保留可见字段（D-04）。"""
    result: list[dict[str, Any]] = []
    for action in actions:
        changed = action.get("changed_fields")
        if not changed:
            result.append(action)
            continue
        filtered = [
            row for row in changed if _keep(row.get("key"), permissions)
        ]
        result.append({**action, "changed_fields": filtered})
    return result
