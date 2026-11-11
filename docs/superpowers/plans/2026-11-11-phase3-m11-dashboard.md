# M11 首页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把占位首页替换为按角色展示的个人工作台 / 管理概览，一次请求取全数据。

**Architecture:** 后端新增 `dashboard` 只读聚合接口，复用现有任务/实例查询；前端拆成 5 个展示组件，`DashboardView` 只负责取数与布局，10 秒轮询刷新。

**Tech Stack:** FastAPI + SQLAlchemy 2 + Pydantic v2；Vue 3 + `<script setup lang="ts">` + Ant Design Vue。

---

### Task 1: 后端首页聚合接口

**Files:**
- Create: `backend/app/schemas/dashboard.py`
- Create: `backend/app/services/dashboard_service.py`
- Create: `backend/app/api/v1/dashboard.py`
- Modify: `backend/app/api/router.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_dashboard.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_dashboard.py`:

```python
"""首页聚合接口（M11）。"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.constants import AssignmentStatus, InstanceStatus, TaskStatus
from app.models import FlowInstance, Task, TaskAssignment
from tests.test_engine_service import _draft_instance, _published_flow, _published_form, _user

BASE = "/api/v1"


def _run_instance(db, initiator, *, status=InstanceStatus.RUNNING, started_at=None, finished_at=None):
    owner = _user(db)
    form = _published_form(db, owner)
    flow = _published_flow(db, owner, form, {"steps": []})
    instance = _draft_instance(db, flow, form, initiator)
    instance.status = status
    instance.started_at = started_at
    instance.finished_at = finished_at
    instance.current_node_keys = ["部门审批"]
    db.flush()
    return instance


def _assign(db, instance, user, *, node_type="approval"):
    task = Task(
        instance_id=instance.id, node_key="s1", node_name="部门审批",
        node_type=node_type, status=TaskStatus.PENDING, blocks_flow=True,
        node_def_snapshot={}, gates=[], activation_seq=1,
    )
    db.add(task)
    db.flush()
    assignment = TaskAssignment(
        task_id=task.id, instance_id=instance.id, user_id=user.id,
        status=AssignmentStatus.PENDING, seq=0,
    )
    db.add(assignment)
    db.flush()
    return assignment


def test_dashboard_requires_login(client):
    assert client.get(f"{BASE}/dashboard/overview").status_code == 401


def test_dashboard_personal_overview(client, db, normal_headers, normal_user):
    instance = _run_instance(db, normal_user)
    _assign(db, instance, normal_user)

    resp = client.get(f"{BASE}/dashboard/overview", headers=normal_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["personal"]["todo"] == 1
    assert body["personal"]["mine_running"] == 1
    assert body["todos"][0]["title"] == "测试单据"
    assert body["todos"][0]["assignment_id"]
    assert body["my_instances"][0]["instance_id"] == instance.id
    assert body["admin"] is None
    assert any(f["name"] == "流程" or f["flow_template_id"] for f in body["quick_flows"])


def test_dashboard_admin_counts(client, db, admin_headers):
    from app.models import User
    from sqlalchemy import select

    admin = db.scalar(select(User).where(User.username == "admin"))
    running = _run_instance(db, admin, started_at=datetime(2026, 11, 11, 8, 0))
    _assign(db, running, admin)
    _run_instance(db, admin, status=InstanceStatus.APPROVED, finished_at=datetime(2026, 11, 11, 9, 0))

    resp = client.get(f"{BASE}/dashboard/overview", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    admin_block = resp.json()["admin"]
    assert admin_block["running"] >= 1
    assert admin_block["pending_backlog"] >= 1
    assert admin_block["by_flow"]


def test_local_bounds_uses_configured_timezone():
    from app.services.dashboard_service import local_bounds

    day, week, month = local_bounds(datetime(2026, 11, 11, 16, 30))  # 本地 11-12 00:30
    assert day == datetime(2026, 11, 11, 16, 0)
    assert week == datetime(2026, 11, 8, 16, 0)   # 周一 11-09 00:00 本地
    assert month == datetime(2026, 10, 31, 16, 0)  # 11-01 00:00 本地
```

- [ ] **Step 2: 跑测试确认失败**

Run: `bash scripts/check.sh backend tests/test_dashboard.py`
Expected: FAIL（`dashboard` 路由不存在 / `local_bounds` 未定义）。

- [ ] **Step 3: 配置时区与依赖**

`backend/app/core/config.py` 增加：

```python
    # ---- 展示时区 ----
    #: 数据统一存 naive UTC；首页「今日/本周/本月」按该时区计算边界
    app_timezone: str = "Asia/Shanghai"
```

`backend/requirements.txt` 增加：

```text
tzdata>=2024.1
```

- [ ] **Step 4: 写 schema**

`backend/app/schemas/dashboard.py`:

```python
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
```

- [ ] **Step 5: 写 service**

`backend/app/services/dashboard_service.py`:

```python
"""首页聚合（M11）。

只读、一次取全：个人计数 + 待办预览 + 我发起的 + 常用流程 + 管理概览。
统计口径复用 task_service / instance_service，不另起一套。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.clock import utcnow
from app.core.config import settings
from app.core.constants import AssignmentStatus, InstanceStatus, TaskType
from app.core.policy import is_designer
from app.models import FlowInstance, FlowTemplate, Task, TaskAssignment, User
from app.services import instance_service, task_service


def local_bounds(now: datetime | None = None) -> tuple[datetime, datetime, datetime]:
    """返回（今日 0 点、本周一 0 点、本月 1 日 0 点）的 **naive UTC** 时间。"""
    moment = now or utcnow()
    tz = ZoneInfo(settings.app_timezone)
    local = moment.replace(tzinfo=UTC).astimezone(tz)
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    week = day - timedelta(days=day.weekday())
    month = day.replace(day=1)

    def to_utc(value: datetime) -> datetime:
        return value.astimezone(UTC).replace(tzinfo=None)

    return to_utc(day), to_utc(week), to_utc(month)


def overview(db: Session, user: User, *, now: datetime | None = None) -> dict:
    day_start, week_start, month_start = local_bounds(now)

    counts = task_service.todo_summary(db, user)
    mine_finished = db.scalar(
        select(func.count(FlowInstance.id)).where(
            FlowInstance.initiator_id == user.id,
            FlowInstance.status == InstanceStatus.APPROVED,
            FlowInstance.finished_at >= month_start,
        )
    ) or 0

    todo_rows = list(
        db.scalars(task_service.build_todo_query(db, user=user).limit(5)).all()
    )
    todos = [
        {
            "assignment_id": row["assignment_id"],
            "instance_id": row["instance_id"],
            "title": row.get("instance_title") or "",
            "code": row.get("instance_code"),
            "node_name": row.get("node_name"),
            "arrived_at": row.get("activated_at"),
        }
        for row in task_service.assignment_rows(db, todo_rows)
    ]

    instances = list(
        db.scalars(
            select(FlowInstance)
            .where(FlowInstance.initiator_id == user.id)
            .order_by(FlowInstance.id.desc())
            .limit(5)
        ).all()
    )
    my_instances = [
        {
            "instance_id": item.id,
            "title": item.title,
            "status": item.status,
            "current_node_names": item.current_node_keys or [],
            "updated_at": item.last_action_at or item.updated_at,
        }
        for item in instances
    ]

    recent_rows = db.execute(
        select(FlowInstance.flow_template_id, func.count(FlowInstance.id))
        .where(FlowInstance.initiator_id == user.id)
        .group_by(FlowInstance.flow_template_id)
    ).all()
    recent = {flow_id: count for flow_id, count in recent_rows}
    available = instance_service.list_available_flows(db, user)
    available.sort(key=lambda item: (-recent.get(item["id"], 0), -item["id"]))
    quick_flows = [
        {"flow_template_id": item["id"], "name": item["name"], "icon": item.get("icon")}
        for item in available[:6]
    ]

    admin = None
    if is_designer(user):
        running = db.scalar(
            select(func.count(FlowInstance.id)).where(
                FlowInstance.status == InstanceStatus.RUNNING
            )
        ) or 0
        submitted_today = db.scalar(
            select(func.count(FlowInstance.id)).where(
                FlowInstance.started_at >= day_start
            )
        ) or 0
        finished_week = db.scalar(
            select(func.count(FlowInstance.id)).where(
                FlowInstance.status == InstanceStatus.APPROVED,
                FlowInstance.finished_at >= week_start,
            )
        ) or 0
        backlog = db.scalar(
            select(func.count(TaskAssignment.id))
            .join(Task, Task.id == TaskAssignment.task_id)
            .where(
                TaskAssignment.status == AssignmentStatus.PENDING,
                Task.node_type != TaskType.CC,
            )
        ) or 0
        by_flow = db.execute(
            select(
                FlowInstance.flow_template_id,
                FlowTemplate.name,
                func.count(FlowInstance.id),
            )
            .join(FlowTemplate, FlowTemplate.id == FlowInstance.flow_template_id)
            .where(FlowInstance.status == InstanceStatus.RUNNING)
            .group_by(FlowInstance.flow_template_id, FlowTemplate.name)
            .order_by(func.count(FlowInstance.id).desc(), FlowInstance.flow_template_id)
            .limit(5)
        ).all()
        admin = {
            "running": running,
            "submitted_today": submitted_today,
            "finished_this_week": finished_week,
            "pending_backlog": backlog,
            "by_flow": [
                {"flow_template_id": flow_id, "name": name, "count": count}
                for flow_id, name, count in by_flow
            ],
        }

    return {
        "personal": {**counts, "mine_finished_this_month": mine_finished},
        "todos": todos,
        "my_instances": my_instances,
        "quick_flows": quick_flows,
        "work_stats": [],
        "admin": admin,
    }
```

- [ ] **Step 6: 写 API 并挂载**

`backend/app/api/v1/dashboard.py`:

```python
"""首页聚合接口（M11）。"""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.dashboard import DashboardOverview
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["首页"])


@router.get("/overview", response_model=DashboardOverview, summary="首页概览")
def overview(db: DbSession, user: CurrentUser) -> dict:
    return dashboard_service.overview(db, user)
```

`backend/app/api/router.py`：import 列表加 `dashboard`，并在 `api_router.include_router(tasks.router)` 后加：

```python
api_router.include_router(dashboard.router)
```

- [ ] **Step 7: 跑测试确认通过**

Run: `bash scripts/check.sh backend tests/test_dashboard.py`
Expected: 4 passed。

- [ ] **Step 8: 提交**

```bash
git add backend/app/core/config.py backend/requirements.txt backend/app/schemas/dashboard.py backend/app/services/dashboard_service.py backend/app/api/v1/dashboard.py backend/app/api/router.py backend/tests/test_dashboard.py
git commit -m "feat(dashboard): 首页聚合接口"
```

---

### Task 2: 前端类型、API 与展示组件

**Files:**
- Create: `frontend/src/types/dashboard.ts`
- Create: `frontend/src/api/modules/dashboard.ts`
- Create: `frontend/src/components/dashboard/StatTiles.vue`
- Create: `frontend/src/components/dashboard/TodoPreviewList.vue`
- Create: `frontend/src/components/dashboard/InstancePreviewList.vue`
- Create: `frontend/src/components/dashboard/QuickFlowGrid.vue`
- Create: `frontend/src/components/dashboard/AdminOverviewPanel.vue`

- [ ] **Step 1: 类型**

`frontend/src/types/dashboard.ts`:

```ts
import type { InstanceStatus } from '@/types/instance'

export interface DashboardStats {
  todo: number
  cc_unread: number
  mine_running: number
  mine_finished_this_month: number
}

export interface DashboardTodoItem {
  assignment_id: number
  instance_id: number
  title: string
  code: string | null
  node_name: string | null
  arrived_at: string | null
}

export interface DashboardInstanceItem {
  instance_id: number
  title: string
  status: InstanceStatus
  current_node_names: string[]
  updated_at: string | null
}

export interface DashboardFlowItem {
  flow_template_id: number
  name: string
  icon: string | null
}

export interface DashboardWorkStatItem {
  sheet_id: number
  name: string
  updated_at: string | null
}

export interface DashboardAdminByFlow {
  flow_template_id: number
  name: string
  count: number
}

export interface DashboardAdmin {
  running: number
  submitted_today: number
  finished_this_week: number
  pending_backlog: number
  by_flow: DashboardAdminByFlow[]
}

export interface DashboardOverview {
  personal: DashboardStats
  todos: DashboardTodoItem[]
  my_instances: DashboardInstanceItem[]
  quick_flows: DashboardFlowItem[]
  work_stats: DashboardWorkStatItem[]
  admin: DashboardAdmin | null
}
```

- [ ] **Step 2: API**

`frontend/src/api/modules/dashboard.ts`:

```ts
import { request } from '@/api/http'
import type { DashboardOverview } from '@/types/dashboard'

export const dashboardApi = {
  overview() {
    return request.get<DashboardOverview>('/dashboard/overview')
  },
}
```

- [ ] **Step 3: 五个展示组件**

`StatTiles.vue`:

```vue
<script setup lang="ts">
import { Card, Col, Row, Statistic } from 'ant-design-vue'

import type { DashboardStats } from '@/types/dashboard'

defineProps<{ stats: DashboardStats }>()
</script>

<template>
  <Row :gutter="[12, 12]">
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="待办" :value="stats.todo" />
      </Card>
    </Col>
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="抄送未读" :value="stats.cc_unread" />
      </Card>
    </Col>
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="我发起的进行中" :value="stats.mine_running" />
      </Card>
    </Col>
    <Col :xs="12" :md="6">
      <Card :bordered="false" class="stat-card">
        <Statistic title="本月已完成" :value="stats.mine_finished_this_month" />
      </Card>
    </Col>
  </Row>
</template>

<style scoped lang="scss">
.stat-card {
  border-radius: 8px;
  height: 100%;

  :deep(.ant-statistic-title) {
    font-size: 12px;
  }
}
</style>
```

`TodoPreviewList.vue`:

```vue
<script setup lang="ts">
import { Card, Empty, List, Tag } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import type { DashboardTodoItem } from '@/types/dashboard'
import { formatDateTime } from '@/utils/datetime'

defineProps<{ todos: DashboardTodoItem[] }>()

const router = useRouter()

function open(item: DashboardTodoItem): void {
  void router.push({
    name: 'instance-detail',
    params: { id: item.instance_id },
    query: { assignment: item.assignment_id },
  })
}
</script>

<template>
  <Card title="我的待办" :bordered="false" class="block">
    <template #extra>
      <a @click="router.push({ name: 'workbench', params: { type: 'todo' } })">全部待办</a>
    </template>

    <List v-if="todos.length" :data-source="todos" size="small">
      <template #renderItem="{ item }">
        <List.Item class="todo-item" @click="open(item)">
          <div class="todo-title">{{ item.title }}</div>
          <div class="todo-meta text-muted">
            <span class="text-mono">{{ item.code }}</span>
            <Tag v-if="item.node_name">{{ item.node_name }}</Tag>
            <span>{{ formatDateTime(item.arrived_at) }}</span>
          </div>
        </List.Item>
      </template>
    </List>
    <Empty v-else description="暂无待办" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
  </Card>
</template>

<style scoped lang="scss">
.todo-item {
  cursor: pointer;
  padding: 10px 0;

  &:hover .todo-title {
    color: #1677ff;
  }
}

.todo-title {
  font-size: 13px;
  font-weight: 500;
}

.todo-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 12px;
}
</style>
```

`InstancePreviewList.vue`:

```vue
<script setup lang="ts">
import { Card, Empty, List, Tag } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import type { DashboardInstanceItem } from '@/types/dashboard'
import { INSTANCE_STATUS_META } from '@/types/instance'
import { formatDateTime } from '@/utils/datetime'

defineProps<{ title: string; instances: DashboardInstanceItem[] }>()

const router = useRouter()

function open(item: DashboardInstanceItem): void {
  void router.push({ name: 'instance-detail', params: { id: item.instance_id } })
}
</script>

<template>
  <Card :title="title" :bordered="false" class="block">
    <template #extra>
      <a @click="router.push({ name: 'workbench', params: { type: 'mine' } })">全部</a>
    </template>

    <List v-if="instances.length" :data-source="instances" size="small">
      <template #renderItem="{ item }">
        <List.Item class="instance-item" @click="open(item)">
          <div class="instance-title">
            {{ item.title }}
            <Tag :color="INSTANCE_STATUS_META[item.status]?.color">
              {{ INSTANCE_STATUS_META[item.status]?.text ?? item.status }}
            </Tag>
          </div>
          <div class="instance-meta text-muted">
            <span v-if="item.current_node_names.length">
              当前：{{ item.current_node_names.join('、') }}
            </span>
            <span>{{ formatDateTime(item.updated_at) }}</span>
          </div>
        </List.Item>
      </template>
    </List>
    <Empty v-else description="还没有发起过单据" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
  </Card>
</template>

<style scoped lang="scss">
.instance-item {
  cursor: pointer;
  padding: 10px 0;

  &:hover .instance-title {
    color: #1677ff;
  }
}

.instance-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
}

.instance-meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
}
</style>
```

`QuickFlowGrid.vue`:

```vue
<script setup lang="ts">
import { RocketOutlined } from '@ant-design/icons-vue'
import { Card, Col, Empty, Row } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import type { DashboardFlowItem } from '@/types/dashboard'

defineProps<{ flows: DashboardFlowItem[] }>()

const router = useRouter()

function start(flow: DashboardFlowItem): void {
  void router.push({
    name: 'start-form',
    params: { flowTemplateId: flow.flow_template_id },
  })
}
</script>

<template>
  <Card title="常用流程" :bordered="false" class="block">
    <template #extra>
      <a @click="router.push({ name: 'start-center' })">发起中心</a>
    </template>

    <Row v-if="flows.length" :gutter="[8, 8]">
      <Col v-for="flow in flows" :key="flow.flow_template_id" :xs="12" :sm="8">
        <button type="button" class="flow-card" @click="start(flow)">
          <RocketOutlined />
          <span class="flow-name">{{ flow.name }}</span>
        </button>
      </Col>
    </Row>
    <Empty v-else description="暂无可发起的流程" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
  </Card>
</template>

<style scoped lang="scss">
.flow-card {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  background: #fff;
  color: rgba(0, 0, 0, 0.75);
  cursor: pointer;
  text-align: left;

  &:hover {
    border-color: #91caff;
    color: #1677ff;
  }
}

.flow-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
```

`AdminOverviewPanel.vue`:

```vue
<script setup lang="ts">
import { Card, Col, Empty, List, Row, Statistic } from 'ant-design-vue'

import type { DashboardAdmin } from '@/types/dashboard'

defineProps<{ admin: DashboardAdmin }>()
</script>

<template>
  <Card title="全局概览" :bordered="false" class="block">
    <Row :gutter="[8, 8]">
      <Col :xs="12" :sm="6">
        <Statistic title="运行中" :value="admin.running" />
      </Col>
      <Col :xs="12" :sm="6">
        <Statistic title="今日提交" :value="admin.submitted_today" />
      </Col>
      <Col :xs="12" :sm="6">
        <Statistic title="本周完成" :value="admin.finished_this_week" />
      </Col>
      <Col :xs="12" :sm="6">
        <Statistic title="待办积压" :value="admin.pending_backlog" />
      </Col>
    </Row>

    <div class="by-flow">
      <div class="text-muted by-flow-title">运行中流程 Top 5</div>
      <List v-if="admin.by_flow.length" :data-source="admin.by_flow" size="small">
        <template #renderItem="{ item }">
          <List.Item>
            <span>{{ item.name }}</span>
            <strong>{{ item.count }}</strong>
          </List.Item>
        </template>
      </List>
      <Empty v-else description="暂无运行中流程" :image="Empty.PRESENTED_IMAGE_SIMPLE" />
    </div>
  </Card>
</template>

<style scoped lang="scss">
.by-flow {
  margin-top: 16px;
}

.by-flow-title {
  font-size: 12px;
  margin-bottom: 4px;
}
</style>
```

- [ ] **Step 4: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit`
Expected: 通过（组件尚未被引用也应有类型检查）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/types/dashboard.ts frontend/src/api/modules/dashboard.ts frontend/src/components/dashboard
git commit -m "feat(web): 首页展示组件与接口类型"
```

---

### Task 3: 首页视图与测试

**Files:**
- Modify: `frontend/src/views/DashboardView.vue`
- Modify: `frontend/src/__tests__/render.spec.ts`

- [ ] **Step 1: 重写 DashboardView**

```vue
<script setup lang="ts">
import { Col, Empty, Row, Spin } from 'ant-design-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { dashboardApi } from '@/api/modules/dashboard'
import AdminOverviewPanel from '@/components/dashboard/AdminOverviewPanel.vue'
import InstancePreviewList from '@/components/dashboard/InstancePreviewList.vue'
import QuickFlowGrid from '@/components/dashboard/QuickFlowGrid.vue'
import StatTiles from '@/components/dashboard/StatTiles.vue'
import TodoPreviewList from '@/components/dashboard/TodoPreviewList.vue'
import { useAuthStore } from '@/stores/auth'
import type { DashboardOverview } from '@/types/dashboard'

const auth = useAuthStore()
const data = ref<DashboardOverview | null>(null)
const loading = ref(false)
const showAdmin = computed(() => auth.isAdmin || auth.isDesigner)

let pollTimer: ReturnType<typeof setInterval> | null = null

async function load(silent = false): Promise<void> {
  if (!silent) loading.value = true
  try {
    data.value = await dashboardApi.overview()
  } catch {
    // 静默：首页失败不应打断其他页面；轮询会自动重试
  } finally {
    if (!silent) loading.value = false
  }
}

onMounted(() => {
  void load()
  pollTimer = setInterval(() => void load(true), 10_000)
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="page-container dashboard">
    <div class="welcome">
      <h2 class="welcome-title">你好，{{ auth.displayName }}</h2>
      <div class="text-muted welcome-meta">
        <span v-if="auth.user?.dept_name">{{ auth.user.dept_name }}</span>
        <span v-if="auth.user?.roles.length">
          {{ auth.user.roles.map((role) => role.name).join(' / ') }}
        </span>
      </div>
    </div>

    <Spin :spinning="loading">
      <template v-if="data">
        <StatTiles :stats="data.personal" />

        <Row :gutter="[12, 12]" class="dashboard-row">
          <Col :xs="24" :lg="14">
            <TodoPreviewList :todos="data.todos" />
          </Col>
          <Col :xs="24" :lg="10">
            <QuickFlowGrid :flows="data.quick_flows" />
          </Col>
        </Row>

        <Row :gutter="[12, 12]" class="dashboard-row">
          <Col :xs="24" :lg="showAdmin && data.admin ? 14 : 24">
            <InstancePreviewList title="我发起的" :instances="data.my_instances" />
          </Col>
          <Col v-if="showAdmin && data.admin" :xs="24" :lg="10">
            <AdminOverviewPanel :admin="data.admin" />
          </Col>
        </Row>
      </template>
      <Empty v-else-if="!loading" description="暂无数据" />
    </Spin>
  </div>
</template>

<style scoped lang="scss">
.dashboard {
  max-width: 1440px;
  margin: 0 auto;
}

.welcome {
  padding: 4px 0 16px;
}

.welcome-title {
  margin: 0;
  font-size: 20px;
}

.welcome-meta {
  display: flex;
  gap: 12px;
  margin-top: 4px;
  font-size: 12px;
}

.dashboard-row {
  margin-top: 12px;
}

.block {
  border-radius: 8px;
  height: 100%;
}
</style>
```

注意：`block` 类需要作用到子组件根元素；scoped 样式对子组件根节点生效（父组件 scope id 会落到根元素），与现有做法一致。

- [ ] **Step 2: 在 render.spec 里 mock dashboard API**

在现有 mock 区域加：

```ts
vi.mock('@/api/modules/dashboard', () => {
  const overview = {
    personal: { todo: 2, cc_unread: 1, mine_running: 1, mine_finished_this_month: 3 },
    todos: [
      { assignment_id: 9, instance_id: 7, title: '出差申请', code: 'CC20261111-0001',
        node_name: '部门审批', arrived_at: '2026-11-11T09:00:00' },
    ],
    my_instances: [
      { instance_id: 7, title: '出差申请', status: 'RUNNING',
        current_node_names: ['部门审批'], updated_at: '2026-11-11T09:00:00' },
    ],
    quick_flows: [{ flow_template_id: 3, name: '请假申请', icon: null }],
    work_stats: [],
    admin: {
      running: 4, submitted_today: 2, finished_this_week: 3, pending_backlog: 5,
      by_flow: [{ flow_template_id: 3, name: '请假申请', count: 2 }],
    },
  }
  return {
    dashboardApi: {
      overview: vi.fn().mockResolvedValue(overview),
    },
  }
})
```

- [ ] **Step 3: 增加首页断言**

在 `render.spec.ts` 末尾新增：

```ts
describe('首页按角色展示', () => {
  async function mountDashboard(asAdmin: boolean) {
    const pinia = createPinia()
    setActivePinia(pinia)
    const auth = useAuthStore(pinia)
    auth.user = {
      id: 1, username: 'u', real_name: '张三', email: null, phone: null,
      dept_id: 1, dept_name: '技术部', position: null, roles: [], last_login_at: null,
    } as never
    auth.isAdmin = asAdmin
    auth.isDesigner = false
    auth.resolved = true

    const router = makeRouter('/')
    await router.push('/')
    await router.isReady()
    return mount(DashboardView, { global: { plugins: [pinia, router, Antd] } })
  }

  it('普通用户看到待办与常用流程', async () => {
    const wrapper = await mountDashboard(false)
    await flushPromises()
    expect(wrapper.text()).toContain('我的待办')
    expect(wrapper.text()).toContain('出差申请')
    expect(wrapper.text()).toContain('常用流程')
    expect(wrapper.text()).not.toContain('全局概览')
    wrapper.unmount()
  })

  it('管理员额外看到全局概览', async () => {
    const wrapper = await mountDashboard(true)
    await flushPromises()
    expect(wrapper.text()).toContain('全局概览')
    expect(wrapper.text()).toContain('待办积压')
    wrapper.unmount()
  })
})
```

- [ ] **Step 4: 跑前端检查**

Run: `cd frontend && npx vue-tsc --noEmit && npx vitest run src/__tests__/render.spec.ts`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/DashboardView.vue frontend/src/__tests__/render.spec.ts
git commit -m "feat(web): 首页改为按角色的工作台"
```

---

### Task 4: 全量校验

- [ ] **Step 1: 跑全量**

Run: `bash scripts/check.sh`
Expected: 五项全绿。

- [ ] **Step 2: 更新三期设计状态**

在 `docs/PHASE3-DESIGN.md` 顶部状态改为 `M11 已完成；M12–M16 待开发`，并在 M11 末尾补实现状态。

- [ ] **Step 3: 提交**

```bash
git add docs/PHASE3-DESIGN.md
git commit -m "docs: M11 首页实现状态"
```
