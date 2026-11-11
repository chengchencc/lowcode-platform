"""v1 路由汇总。新增模块时在此挂载。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    audit,
    auth,
    dashboard,
    delegations,
    departments,
    files,
    flow_templates,
    flow_versions,
    form_templates,
    form_versions,
    health,
    instances,
    notifications,
    roles,
    spreadsheets,
    tasks,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(departments.router)
api_router.include_router(roles.router)
api_router.include_router(audit.router)

# M2 表单
api_router.include_router(form_templates.router)
api_router.include_router(form_versions.router)
api_router.include_router(files.router)

# M3 流程
api_router.include_router(flow_templates.router)
api_router.include_router(flow_versions.router)

# M4 发起与工作台
api_router.include_router(instances.router)
api_router.include_router(tasks.router)
api_router.include_router(dashboard.router)
api_router.include_router(notifications.router)

api_router.include_router(delegations.router)
api_router.include_router(ai.router)
api_router.include_router(spreadsheets.router)
