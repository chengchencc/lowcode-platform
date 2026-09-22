"""v1 路由汇总。新增模块时在此挂载。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import audit, auth, departments, health, roles, users

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(departments.router)
api_router.include_router(roles.router)
api_router.include_router(audit.router)

# M2: form_templates / form_versions
# M3: flow_templates / flow_versions / instances / tasks / notifications / files
