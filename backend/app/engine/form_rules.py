"""表单字段联动规则求值（M9）。

规则只能**收紧**权限：hidden / readonly / required。节点权限矩阵已经隐藏的字段，
规则不能把它重新点亮；只读字段也不能被规则改成可编辑。

语义与前端 `src/utils/formRules.ts` 共用 `docs/form-rule-test-vectors.json` 的向量。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.engine.conditions import evaluate_group
from app.engine.permissions import FieldPermission


def _restrict(
    perm: FieldPermission,
    effect: str,
    rule_id: str,
) -> FieldPermission:
    reason = f"{perm.reason} → R{rule_id}:{effect}" if perm.reason else f"R{rule_id}:{effect}"

    if effect == "hidden":
        return FieldPermission(False, False, False, reason)

    if effect == "readonly":
        if not perm.visible:
            return perm
        return FieldPermission(True, False, False, reason)

    if effect == "required":
        # 只读/隐藏字段上的必填没有意义
        if not perm.visible or not perm.editable:
            return perm
        return FieldPermission(True, True, True, reason)

    return perm


def apply_form_rules(
    permissions: Mapping[str, FieldPermission],
    form_schema: Any,
    values: Mapping[str, Any] | None = None,
) -> dict[str, FieldPermission]:
    """在基础权限之上应用表单规则，返回新的权限表。"""
    result = dict(permissions)
    values = values or {}
    for rule in getattr(form_schema, "rules", []) or []:
        if not evaluate_group(rule.when, values):
            continue
        for effect in rule.effects:
            current = result.get(effect.target)
            if current is None:
                continue
            result[effect.target] = _restrict(current, effect.effect, rule.id)
    return result


def hidden_clear_keys(
    base_permissions: Mapping[str, FieldPermission],
    form_schema: Any,
    values: Mapping[str, Any] | None = None,
) -> set[str]:
    """需要因 `clear_when_hidden` 清空的字段。

    只清「基础权限本来可见」的字段 —— 本来就是隐藏的旧值不属于这条规则负责。
    """
    values = values or {}
    out: set[str] = set()
    for rule in getattr(form_schema, "rules", []) or []:
        if not rule.clear_when_hidden:
            continue
        if not evaluate_group(rule.when, values):
            continue
        for effect in rule.effects:
            if effect.effect != "hidden":
                continue
            current = base_permissions.get(effect.target)
            if current is not None and current.visible:
                out.add(effect.target)
    return out


__all__ = ["apply_form_rules", "hidden_clear_keys"]
