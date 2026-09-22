"""顶层生命周期状态机（PRD §3.5.1）。

**这只是「用户可感知的业务状态」**。真正的并行语义由节点级令牌承载
（见 router.py），顶层状态是令牌集合的投影：

    DRAFT ──提交──> RUNNING ──┬─ 结束节点完成 ──> APPROVED
                              ├─ 驳回          ──> REJECTED ──重提──> RUNNING
                              ├─ 撤回          ──> WITHDRAWN
                              └─ 管理员终止     ──> TERMINATED

把状态机单独成一个模块，是为了让「哪些迁移合法」能脱离令牌体系单独测 ——
非法迁移（如 REJECTED → APPROVED）必须报错而不是静默通过。
"""

from __future__ import annotations

from app.core.constants import TERMINAL_STATUSES, InstanceStatus
from app.engine.errors import IllegalTransition

#: 事件名。与 REST 动作一一对应。
EVENT_SUBMIT = "SUBMIT"
EVENT_RESUBMIT = "RESUBMIT"
EVENT_FINISH = "FINISH"        # 走到结束节点
EVENT_REJECT = "REJECT"
EVENT_WITHDRAW = "WITHDRAW"
EVENT_ABANDON = "ABANDON"      # 驳回后放弃
EVENT_TERMINATE = "TERMINATE"
EVENT_DELETE_DRAFT = "DELETE_DRAFT"

#: 状态 → {事件: 目标状态}
TRANSITIONS: dict[str, dict[str, str]] = {
    InstanceStatus.DRAFT: {
        EVENT_SUBMIT: InstanceStatus.RUNNING,
        EVENT_DELETE_DRAFT: InstanceStatus.WITHDRAWN,
        EVENT_TERMINATE: InstanceStatus.TERMINATED,
    },
    InstanceStatus.RUNNING: {
        EVENT_FINISH: InstanceStatus.APPROVED,
        EVENT_REJECT: InstanceStatus.REJECTED,
        EVENT_WITHDRAW: InstanceStatus.WITHDRAWN,
        EVENT_TERMINATE: InstanceStatus.TERMINATED,
    },
    InstanceStatus.REJECTED: {
        # 重新提交：从头重走全流程（PRD §3.5.4）
        EVENT_RESUBMIT: InstanceStatus.RUNNING,
        EVENT_ABANDON: InstanceStatus.WITHDRAWN,
        EVENT_TERMINATE: InstanceStatus.TERMINATED,
    },
    # 终态没有出边：REJECTED → APPROVED 这类迁移必须失败
    InstanceStatus.APPROVED: {},
    InstanceStatus.WITHDRAWN: {},
    InstanceStatus.TERMINATED: {},
}


def can_transition(current: str, event: str) -> bool:
    return event in TRANSITIONS.get(current, {})


def next_status(current: str, event: str) -> str:
    """计算迁移后的状态；非法迁移抛 `IllegalTransition`。"""
    target = TRANSITIONS.get(current, {}).get(event)
    if target is None:
        raise IllegalTransition(current, event)
    return target


def is_terminal(status: str) -> bool:
    return status in TERMINAL_STATUSES


def is_editable(status: str) -> bool:
    """该状态下发起人还能修改表单数据吗。"""
    return status in {InstanceStatus.DRAFT, InstanceStatus.REJECTED}


def assert_transition(current: str, event: str) -> str:
    """带更友好信息的迁移校验。"""
    if is_terminal(current):
        raise IllegalTransition(current, f"{event}（实例已处于终态，不能再变更）")
    return next_status(current, event)
