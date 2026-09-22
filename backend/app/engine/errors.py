"""引擎异常。

这些异常表示**流程定义或引擎状态有问题**，不是用户输入错误 ——
用户层面的错误（如「有人处理过之后不能撤回」）用 `app.core.errors` 里的业务异常。
"""

from __future__ import annotations


class EngineError(Exception):
    """引擎基类异常。"""


class FlowInvalid(EngineError):
    """流程定义结构非法（编译期发现）。"""

    def __init__(self, message: str, *, node_id: str | None = None) -> None:
        self.node_id = node_id
        super().__init__(message)


class IllegalTransition(EngineError):
    """非法的状态迁移（如 REJECTED → APPROVED）。"""

    def __init__(self, current: str, action: str) -> None:
        self.current = current
        self.action = action
        super().__init__(f"实例处于 {current} 状态，不能执行 {action}")


class TokenConflict(EngineError):
    """令牌状态与预期不符（并发或重复提交）。"""


class PermissionDenied(EngineError):
    """无权执行该动作。"""


class ApproverUnresolved(EngineError):
    """审批人解析未命中，且策略要求阻断。"""


class ExpressionError(EngineError):
    """条件表达式语法或求值错误。"""
