"""通用 DTO。

命名约定：全链路 **snake_case**（含存库的 JSON 定义与前端 TS 类型）。
PRD 的示例 JSON 用了 camelCase，实现时统一转成 snake_case，
避免同一份数据在 Python / JSON / TS 三处各有一套命名规则。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IdResp(BaseModel):
    id: int


class OkResp(BaseModel):
    ok: bool = True
    message: str | None = None


class IdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class MembersRequest(BaseModel):
    """部门/角色的成员整体覆盖式更新。"""

    user_ids: list[int] = Field(default_factory=list)


class OptionItem(BaseModel):
    """下拉选项（带 id 的字典项）。"""

    label: str
    value: str | int
