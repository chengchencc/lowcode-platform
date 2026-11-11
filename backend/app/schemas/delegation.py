"""转办与委托的 DTO（M14）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class DelegationCreate(BaseModel):
    delegatee_id: int
    start_at: datetime
    end_at: datetime
    flow_template_ids: list[int] | None = None
    reason: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _check_range(self) -> DelegationCreate:
        if self.start_at >= self.end_at:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class DelegationUpdate(BaseModel):
    delegatee_id: int | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    flow_template_ids: list[int] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=512)


class DelegationOut(BaseModel):
    id: int
    delegator_id: int
    delegator_name: str | None = None
    delegatee_id: int
    delegatee_name: str | None = None
    start_at: datetime
    end_at: datetime
    flow_template_ids: list[int] | None = None
    reason: str
    status: str
    created_at: datetime | None = None


class TransferRequest(BaseModel):
    to_user_id: int
    reason: str = Field(min_length=1, max_length=512)
