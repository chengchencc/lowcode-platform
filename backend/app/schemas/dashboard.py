"""首页聚合接口的 DTO（M11）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DashboardStats(BaseModel):
    todo: int = 0
    cc_unread: int = 0
    mine_running: int = 0
    mine_finished_this_month: int = 0


class DashboardTodoItem(BaseModel):
    assignment_id: int
    instance_id: int
    title: str
    code: str | None = None
    node_name: str | None = None
    arrived_at: datetime | None = None


class DashboardInstanceItem(BaseModel):
    instance_id: int
    title: str
    status: str
    current_node_names: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class DashboardFlowItem(BaseModel):
    flow_template_id: int
    name: str
    icon: str | None = None


class DashboardWorkStatItem(BaseModel):
    sheet_id: int
    name: str
    updated_at: datetime | None = None


class DashboardAdminByFlow(BaseModel):
    flow_template_id: int
    name: str
    count: int


class DashboardAdmin(BaseModel):
    running: int = 0
    submitted_today: int = 0
    finished_this_week: int = 0
    pending_backlog: int = 0
    by_flow: list[DashboardAdminByFlow] = Field(default_factory=list)


class DashboardOverview(BaseModel):
    personal: DashboardStats
    todos: list[DashboardTodoItem] = Field(default_factory=list)
    my_instances: list[DashboardInstanceItem] = Field(default_factory=list)
    quick_flows: list[DashboardFlowItem] = Field(default_factory=list)
    #: M12 工作量统计上线后填充；M11 恒为空数组
    work_stats: list[DashboardWorkStatItem] = Field(default_factory=list)
    admin: DashboardAdmin | None = None
