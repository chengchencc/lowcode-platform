"""AI 辅助配置的 DTO（M15）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AiFormRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    preferences: str | None = Field(default=None, max_length=500)


class AiFlowRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    form_schema: dict[str, Any]


class AiFormResponse(BaseModel):
    schema_data: dict[str, Any]


class AiFlowResponse(BaseModel):
    definition: dict[str, Any]


class AiStatusOut(BaseModel):
    enabled: bool
    model: str | None = None
