# FlowForm 技术设计文档

> 配套：`PRD-lowcode-form-approval.md`。本文是编码依据，随实现推进增量修订。
> **当前状态：M1 已实现**，M2–M6 为已定稿设计。

---

## 0. 与 PRD 的偏离

| # | PRD 原定 | 实际 | 原因 |
|---|---|---|---|
| 1 | §10 #2 前端组件库 Element Plus | **Ant Design Vue 4.x** | 用户指定。连带影响见 §7.3 |
| 2 | §6 目标库 MySQL 8 | 开发期 **SQLite**，切 MySQL 只改连接串 | 用户指定。为守住 §6 的目标形态，全部模型与迁移必须方言无关（D1） |
| 3 | §10 #1 FastAPI（异步） | FastAPI + **同步** SQLAlchemy | 见 D2。千级用户规模下同步会话完全够用，省掉 async session 与 alembic 的适配成本，引擎单测也更好写 |

---

## 1. 关键决策

| # | 决策 | 理由 / 影响 |
|---|---|---|
| **D1** | **模型与迁移全程无 MySQL 专有 DDL** | 切换库只改 `DATABASE_URL`。详见 §2.4 |
| **D2** | 同步 SQLAlchemy 2.0 | 见上表 #3 |
| **D3** | 迁移按里程碑增量建表 | M1 只建组织表；引擎设计在 M3 仍可能微调，不必提前冻结全部 16 张表 |
| **D4** | 枚举存 `String`，Python 侧用 `StrEnum` | SQLite 无原生 ENUM；加值不需改表 |
| **D5** | 密码用 `bcrypt` 库直接调用，不用 passlib | passlib 已停更，且与 bcrypt 4.x 有已知告警 |
| **D6** | JWT 用 `PyJWT` | 比 python-jose 维护更活跃 |
| **D7** | 前端写操作自动带 `X-Request-Id` | PRD §7 幂等要求的入口层基础；后端 M3 落到 `instance_actions.request_id` 唯一索引 |
| **D8** | 根组件 `<a-app>` + `App.useApp()` | antd 4 的 message/Modal 静态方法不消费 ConfigProvider 上下文，中文 locale 会丢 |
| **D9** | **时间一律 naive UTC，由应用层生成** | SQLite 的 `CURRENT_TIMESTAMP` 是 UTC、MySQL 的 `NOW()` 是会话时区，用数据库默认值会让开发库与生产库差 8 小时。前端负责补 `Z` 再转本地（`utils/datetime.ts`） |
| **D10** | 全链路 **snake_case** | PRD 示例 JSON 用了 camelCase。统一成 snake_case，避免同一份数据在 Python/JSON/TS 三处三套命名 |
| **D11** | 前端**不做**组件自动导入 | 自动导入生成的 `.d.ts` 在全新 clone 上不存在，会让 `vue-tsc` 先于 `vite build` 失败。显式 import 换来零生成物依赖 |

---

## 2. 分层与目录结构

```
lowcode-platform/
├─ docker-compose.dev.yml        # 仅 mysql8 + adminer（默认走 SQLite，切库时才用）
├─ docs/
│  ├─ PRD-lowcode-form-approval.md
│  └─ TECH-DESIGN.md
├─ backend/
│  ├─ requirements.txt / requirements-dev.txt
│  ├─ pyproject.toml             # ruff + pytest 配置
│  ├─ alembic.ini                # ★ 必须保持纯 ASCII，见 §9
│  ├─ alembic/env.py             # 连接串唯一来源 = app.core.config
│  ├─ alembic/versions/0001_m1_org_tables.py
│  ├─ app/
│  │  ├─ main.py                 # 应用装配 + 启动种子
│  │  ├─ core/                   # config / clock / constants / errors / security
│  │  │  └─ policy.py            # 授权判定（Protocol 化，core 不依赖 models）
│  │  ├─ db/                     # base.py(可移植类型) / session.py
│  │  ├─ models/                 # org.py / audit.py
│  │  ├─ schemas/                # Pydantic DTO
│  │  ├─ services/               # 业务编排
│  │  ├─ api/v1/                 # 路由
│  │  └─ seeds/init_admin.py     # F6.5 幂等种子
│  └─ tests/
└─ frontend/
   ├─ src/api/                   # http.ts(拦截器/刷新/幂等键) + modules/
   ├─ src/stores/                # auth / app / org
   ├─ src/router/                # index.ts(路由表) + guards.ts
   ├─ src/layouts/DefaultLayout.vue
   ├─ src/views/                 # Login / Dashboard / NotFound / admin/**
   ├─ src/components/common/     # UserSelect（M2 表单控件会复用）
   ├─ src/directives/permission.ts
   └─ src/utils/                 # feedback / datetime
```

### 依赖方向（M3 起用 import-linter 在 CI 校验）

```
api → services → engine/db
engine 不得 import api / services
engine 的纯函数核心（compile / conditions / expressions / permissions /
aggregate / machine / router）不得 import db
```

**为什么单独强调**：引擎语义（PRD §3.5）必须能脱离数据库做单测。一旦纯核心 import 了 `Session`，测试就得起库，M3 的单测矩阵会很痛苦。

---

## 3. 数据模型

### 3.1 表 → 里程碑归属

| 表 | 里程碑 | 状态 |
|---|---|---|
| `departments` / `users` / `roles` / `user_roles` / `audit_logs` | M1 | ✅ 已建（`0001_m1_org_tables.py`） |
| `form_templates` / `form_versions` | M2 | 待建 |
| `flow_templates` / `flow_versions` | M3 | 待建 |
| `flow_instances` / `instance_ext_fields` | M3 / M5 | 待建 |
| `tasks` / `task_assignments` | M3 | 待建 |
| `instance_actions` / `data_snapshots` | M3 | 待建 |
| `notifications` / `attachments` | M4 | 待建 |

### 3.2 M1 已落地的设计要点

- **`departments` 用物化路径**：`path` 形如 `/1/4/9/`，子树查询 = `path LIKE '/1/4/%'`，两种数据库上都简单且够快。`level` 冗余存储，移动子树时整体偏移。
- **`departments.manager_user_id` 刻意不建外键**：它与 `users.dept_id` 互相引用会成环，环外键在 SQLite 上要靠批处理重建表。完整性由 `dept_service._assert_manager_valid` 保证，删除用户时由 `user_service.delete` 清理悬挂引用。
- **`users.token_version`**：改密 / 停用 / 登出 / 重置密码都 +1，使已签发 JWT 立即失效（F6.4）。这是「改密后其他浏览器被踢下线」的实现方式。
- **`audit_logs` 无 `updated_at`、`actor_id` 无外键**：追加写、不可篡改；用户删除后审计仍须可读，故同时冗余 `actor_name` 快照。

### 3.3 后续表的设计定稿（M2–M5 落地时照此建）

**幂等与并发落点**（PRD §6 / §7 的落地）：

| 层面 | 机制 |
|---|---|
| HTTP 重放 | `instance_actions.request_id` 唯一索引；重复请求返回既有结果 |
| 同人同任务重复提交 | `instance_actions` 唯一键 `(instance_id, task_id_nn, actor_id, action_seq)` |
| 派发幂等 | `task_assignments` 唯一键 `(task_id, user_id, seq)` |
| 通知幂等 | `notifications.dedup_key` 唯一索引（形如 `TASK:123:U:5`） |
| 实例级互斥 | 事务内 `SELECT ... FOR UPDATE` 锁 `flow_instances` 行 |
| 客户端乐观锁 | `flow_instances.version` / `task_assignments.version`，不匹配 → 409 `STALE_VERSION` |

> **不用 MySQL generated column**：`instance_actions.task_id` 设计为 `NOT NULL DEFAULT 0`，`0` 表示「实例级动作」（撤回/终止/追加字段），以此替代 `COALESCE(task_id,0)` 生成列 —— SQLite 不支持生成列。

---

## 4. 引擎设计（M3，本文档最关键部分）

### 4.1 双层模型

```
顶层：实例生命周期状态机（用户可感知）
底层：节点执行器 + 并行令牌（Token）—— 每个待办任务即一个活跃令牌
```

**为什么不能只用状态机**：状态机是单一快照，无法表达「财务 A 与财务 B 两个任务同时挂起、各自独立完成」。

### 4.2 令牌的落地映射

| 概念 | 落地 |
|---|---|
| 活跃令牌 | `tasks` 行，`status='PENDING' AND blocks_flow=1` |
| 令牌位置 | `(node_key, gates, activation_seq, round)` |
| 节点进行中 | 该 task 的 assignments 中 ≥1 为 `PENDING` |
| 抄送知会 | `tasks.node_type='CC'`，`blocks_flow=0`（不占令牌、不计进度、主线不等） |
| 并行组成员 | 同 `group_id` 的多个 `tasks` 行 |
| 会签 all / 或签 any | 1 个 `tasks` 行 + N 个 `task_assignments`（`assignee_mode=ALL/ANY`） |
| 依次审批 | 1 个 `tasks` 行 + N 个 assignments，`seq` 升序，仅最小 seq 为 `PENDING`，其余 `WAITING` |

`gates` 是分支决策链（如 `["s2:s2a"]`），是祖先判定的唯一依据 —— 退回/取消范围计算因此可以写成纯函数，好测。

### 4.3 引擎事件表（提交/动作 → 令牌集合变化）

`EngineService` 的每个公开方法是一次事务化事件。此表既是语义契约，也是单测断言清单。

| 事件 | 触发者 | 前置校验 | 令牌操作 | 顶层状态 |
|---|---|---|---|---|
| `SUBMIT` | 发起人 | status ∈ {DRAFT, REJECTED}；字段校验；`initiator_select` 已选人 | 从 start 展开，spawn 首个节点（条件分支递归求值） | DRAFT/REJECTED → RUNNING |
| `RESUBMIT` | 发起人 | status=REJECTED | `round += 1`，从 start 重新 spawn | REJECTED → RUNNING |
| `AGREE`（未满足聚合） | 处理人 | assignment PENDING | 无令牌变化；SEQUENTIAL 激活下一个 | 不变 |
| `AGREE`（节点完成） | 处理人 | 聚合达成 DONE | 本 task → COMPLETED；`plan_after_node` spawn 后继 | 不变 |
| `AGREE`（实例完成） | 处理人 | 后继命中 end | 本 task → COMPLETED | RUNNING → APPROVED |
| `AGREE`（或签达成） | 处理人 | mode=ANY | 其余 assignments → CANCELLED(`ANY_SIGN_DONE`) | 同上 |
| `REJECT` | 审批节点处理人 | `rejectPolicy` 允许 | 取消**全部** PENDING 令牌 | RUNNING → REJECTED |
| `RETURN` | 审批/填写处理人 | `target ∈ allowed_return_targets()` | 取消 target 之后的全部令牌；target 上 `activation_seq+1` 重派 | **不变（仍 RUNNING）** |
| `WITHDRAW` | 发起人 | **不存在任何 DONE 的 assignment**（抄送已读不算） | 取消全部 PENDING | RUNNING → WITHDRAWN |
| `ABANDON` | 发起人 | status=REJECTED | 无活跃令牌 | REJECTED → WITHDRAWN |
| `TERMINATE` | 管理员 | reason 必填 | 取消全部 PENDING | * → TERMINATED |
| `CC_READ` | 被抄送人 | — | 无 | 不变 |
| `ADD_EXT_FIELD` | 管理员/设计者 | 实例未终态 | 更新实例 schema | 不变 |

### 4.4 退回的取消规则（唯一一条，覆盖全部退回场景）

```
保留：pending 令牌的 gates 是 target.gates 的严格前缀，且 token 在 target 的祖先链上
取消：其余全部（含 target 自身待办、并行组成员、或签其余、目标之后的顺序节点）
随后：在 target 上 activation_seq + 1 重新 spawn
```

由此自然满足 PRD：「取消被退回节点及后续全部令牌；已通过的更早节点不重走；字段数据保留（**不回滚 `current_data`**）」。

> **需评审确认的取舍**：若退回目标位于并行组之前，该组会被**整组重派**（含此前已同意的成员）。这是 PRD 原文「取消后续全部令牌」的直接后果；替代方案（只重派未完成成员）会让组语义出现「半激活」状态，V1 不采用。

### 4.5 字段权限矩阵求值（PRD §3.4 机制 A/B）

求值顺序，**后者覆盖前者**（允许 hidden → editable 反向点亮，这是机制 B 的关键）：

| 层 | 规则 |
|---|---|
| L0 节点类型默认 | `start`：`field.visible_at_start ? editable : hidden`；审批/填写/抄送：`stage=='apply' ? readonly : hidden` |
| L1 分区批量 | `fields_permission.partitions[section_key]`（缺省用 `base`） |
| L2 单字段覆盖 | `fields_permission.overrides[field_key]`（子表列为 `items[].amount` 形式） |
| L3 条件覆盖 | `conditional_overrides[]` 按声明序求值，命中即覆盖 |
| L4 模板级标记 | `field.required` → `required=True`；`editable-required` ≡ `editable + required` |
| L5 扩展字段（机制 C） | `visible_from_node_id` 在祖先链之后且 ACTIVE 才可见；仅 `editable_node_ids` 内可编辑，其余只读 |
| 查看者维度 | 非当前处理人且实例已终态 → 全部 `visible + readonly`（支撑「申请人全程看不到补充字段，通过后归档可见」） |

返回值带 `reason` 字段（如 `"L1:partitions[sec_supplement]=hidden"`），供前端提示与设计器冲突高亮（F2.3）。

**实例数据存储**（PRD §3.4 末尾实现提示的三元组）：

| 元素 | 位置 |
|---|---|
| 模板 schema 值 | `flow_instances.current_data` |
| 扩展字段定义 | `instance_ext_fields` 行 + 合并进 `flow_instances.data_schema` |
| 扩展字段值 | 同 `current_data`（`ext_` 前缀保证不与模板字段冲突） |
| 写入来源追踪 | `flow_instances.field_meta = {key: {node, actor_id, at, action_id, round}}` |
| 历史时点 | `data_snapshots.data = {values, ext_fields}`（模板 schema 由不可变的 `form_versions` 提供，无需复制） |

### 4.6 引擎核心签名

```python
# engine/service.py —— 唯一写入口
class EngineService:
    def save_draft(...) -> FlowInstance
    def submit(*, instance, actor, data, note, attachment_ids, assignee_picks, request_id) -> EngineResult
    def resubmit(...) -> EngineResult
    def act(*, assignment_id, actor, action, opinion, attachment_ids, field_patch,
            return_target, expected_version, request_id) -> EngineResult
    def withdraw / abandon / terminate / delete_draft(...) -> EngineResult | None
    def add_ext_field / disable_ext_field(...) -> EngineResult
    def mark_cc_read(*, assignment_id, actor) -> None

# 内部原语（全部在持有实例行锁的事务内）
_lock_instance / _spawn / _cancel / _advance / _next_action_seq / _emit_events

# engine/router.py —— 纯函数
plan_start / plan_after_node / plan_after_group / ancestors
allowed_return_targets / cancel_set_for_return

# engine/aggregate.py —— 纯函数
node_state(mode, assignments) -> OPEN|DONE|FAILED
group_state(members)         -> OPEN|JOINED|FAILED
next_sequential_index(assignments) -> int | None

# engine/permissions.py —— 纯函数
resolve_field_permissions(...) -> dict[str, FieldPermission]
resolve_view_permissions(...)  # 归档/抄送/非处理人视角
apply_field_patch(instance, patch, *, node_id, actor_id, action_id, permissions)
```

所有公开方法统一骨架：
`锁实例 → 状态机 guard → 幂等检查(request_id/action_seq) → 计算 TokenOp → 落库 → 写 action/snapshot → 生成通知 → 提交`

---

## 5. API 契约

约定：前缀 `/api/v1`；认证 `Authorization: Bearer <jwt>`；分页 `?page=1&size=20`；
错误体固定 `{"detail": {"code", "message", "extra"?}}`；写接口自动带 `X-Request-Id`。

### 5.1 M1 已实现

| 模块 | 端点 |
|---|---|
| 认证 | `POST /auth/login` `POST /auth/refresh` `POST /auth/logout` `GET /auth/me` `POST /auth/change-password` |
| 用户 | `GET/POST /users`、`GET/PUT/DELETE /users/{id}`、`POST /users/{id}/reset-password`、`POST /users/{id}/status`、`POST /users/import`、`GET /users/options` |
| 部门 | `GET /departments/tree`、`GET /departments/options`、`POST /departments`、`GET/PUT/DELETE /departments/{id}`、`GET/PUT /departments/{id}/members` |
| 角色 | `GET/POST /roles`、`GET/PUT/DELETE /roles/{id}`、`GET/PUT /roles/{id}/members` |
| 审计 | `GET /admin/audit-logs` |
| 探活 | `GET /healthz` `GET /readyz` |

### 5.2 鉴权依赖

| 依赖 | 语义 |
|---|---|
| `CurrentUser` | 解析 JWT、校验 `token_version`、注入 `User` |
| `AdminUser` | `is_superuser ∨ 角色 platform_admin` |
| `DesignerUser` | `is_admin ∨ 角色 designer`（管理员天然通过） |
| `get_instance(id, level)`（M3） | `view`：发起人 ∨ 有 assignment ∨ 被抄送 ∨ 管理员；`act`：assignment 属己且 PENDING；`manage`：管理员 |

### 5.3 M2–M4 端点规划

- **表单**：`/form-templates`、`/form-templates/{id}/versions`、`/form-versions/{vid}`、
  `/{vid}/validate`、`/{vid}/publish`、`/{vid}/preview`、`/form-templates/{id}/export|import`
- **流程**：`/flow-templates`、`/{id}/versions`、`/flow-versions/{vid}`、`/{vid}/validate`、
  `/{vid}/publish`（锁定表单版本）、`/{vid}/preview-permissions`、`/{vid}/return-targets`
- **实例**：`POST /instances/drafts`、`GET /instances/drafts`、`POST /instances/{id}/submit|resubmit|withdraw|abandon|terminate`、
  **`GET /instances/{id}/render`（详情页一次取全）**、`/{id}/progress`、`/{id}/timeline`、`/{id}/snapshots/{sid}`、`/{id}/snapshots/diff`、`POST /instances/{id}/ext-fields`
- **任务**：`GET /tasks/todo|done|cc|mine`、`GET /tasks/assignments/{aid}`、`/{aid}/return-targets`、
  **`POST /tasks/assignments/{aid}/act`（统一动作接口）**、`/{aid}/diff-preview`、`/{aid}/read`
- **消息/文件**：`/notifications`、`/notifications/unread-count`、`POST /files/upload`、`GET /files/{id}/download`

---

## 6. 前端结构

### 6.1 路由表

| path | name | meta | 里程碑 |
|---|---|---|---|
| `/login` | login | — | M1 |
| `/dashboard` | dashboard | — | M1 |
| `/admin/org/users` `/depts` `/roles` | org-* | `adminOnly` | M1 |
| `/admin/audit` | audit | `adminOnly` | M1 |
| `/start-center` `/start/:flowTemplateId` | — | — | M2/M4 |
| `/workbench/:type(todo\|done\|mine\|cc)` | — | — | M4 |
| `/instance/:id` | — | — | M4 ★核心页面 |
| `/admin/forms[/:id/design]` `/admin/flows[/:id/design]` `/admin/instances` | — | `roles:['designer']` | M2/M3 |
| `/messages` | — | — | M4 |

M2–M4 的菜单项已在 `DefaultLayout.vue` 中以**禁用态占位**，导航结构与 PRD §5 保持一致。

### 6.2 三个核心组件（M2–M4）

1. **通用表单渲染器** `components/form-renderer/`
   **单一渲染树，三态由服务端下发的 `permissions` 驱动，禁止分叉实现**：
   `FormRenderer → SectionBlock（分区全 hidden 则整块不渲染）→ FieldWrapper（hidden 时 return null）→ FieldControl（按 type 查注册表）`；
   另有 `SubtableControl` / `AttachmentControl` / `OrgPickerControl` / `FormulaControl`。
   被**发起页、实例详情、快照回放、设计器预览**四处复用。

2. **流程配置器** `components/flow-designer/`
   三栏：左节点清单树（顺序 + 条件分支嵌套 + 并行组子节点）、中属性面板
   （`ApproverPanel` / `FieldPermPanel` / `ConditionPanel` / `CcPanel`）、右实时预览。

3. **实例详情页** `components/instance/`
   `InstanceHeader + ProgressBar（并行组子节点并列）+ SectionForm（委托 FormRenderer）+
   ActionPanel + TimelineList + SnapshotDialog + DiffViewer + ExtFieldDialog`。
   装配顺序：`loadRender(instanceId, assignmentId?)` → 渲染各部分。

### 6.3 D8 的落地（Ant Design Vue 特有）

`App.vue` 用 `<a-config-provider :locale="zhCN"><a-app>` 包裹，`AppFrame.vue` 作为
`<a-app>` 的**子组件**调用 `App.useApp()` 并把实例注册到 `utils/feedback.ts`，
供 axios 拦截器与 store 等非组件代码使用。

> 换成 Element Plus 需要重写的点：控件注册表、`a-form` 的 `rules`/`name` 路径校验
> 对接方式（与 EP 的 `prop` 模型不同）、`a-table` 的 `columns` + `#bodyCell` 插槽风格。
> 因此设计器与渲染器里对组件库的依赖要收敛在 `form-renderer/controls/` 一层内。

---

## 7. 里程碑落地顺序

| 里程碑 | 步骤 | 验收 |
|---|---|---|
| **M1** ✅ | 仓库骨架 → 迁移 → 模型/安全/认证 → 组织 CRUD → 前端框架与组织三页 | 可登录、可维护组织（62 项测试 + 30 项端到端冒烟通过） |
| **M2** | ①`form_schema` 校验 + `form_service` ②表单配置器 ③`expressions.py`（公式，纯后端先行）④通用表单渲染器 ⑤预览 | 能配出报销单表单 |
| **M3** | ①`types/compile/conditions/machine/router` + 单测 ②`permissions.py` + 单测 ③`aggregate/approvers` + 单测 ④`validate.py` 校验器 ⑤`service.py` 事务编排 + 集成测试 ⑥流程配置器 | 单测覆盖 §4.3 语义矩阵；可发布报销流程 |
| **M4** | ①草稿/提交/重提 ②`render/timeline/task_service` ③发起中心与发起页 ④工作台四列表 + 实例详情页 ⑤撤回/撤销/终止 ⑥站内通知与角标轮询 | **PRD §9 场景一（请假）端到端跑通** |
| **M5** | ①驳回重提轮次与快照对照 ②机制 C 追加字段 ③公式与级联下拉补齐 ④消息中心打磨 | **PRD §9 场景二（报销）端到端跑通** |
| **M6** | ①示例流程库 ②归档列表与导出 ③审计查询打磨 ④Docker 一键起 ⑤文档与演示 | 可交付内部试用 |

---

## 8. 测试策略

**M1 现状**：62 项 pytest（认证 / 用户 / 部门 / 角色 / 审计）+ `ruff check` 全绿 + `vue-tsc` 无错。

**隔离机制**：每个测试跑在一个外层事务里，结束后回滚。用 SQLAlchemy 2.0 的
`join_transaction_mode="create_savepoint"`，业务代码里的 `session.commit()`
只释放 savepoint —— 既保留真实提交行为，又保证测试互不污染。**必须配合
`tests/conftest.py` 里关掉 pysqlite 隐式事务的那两个事件监听器**，否则最外层
savepoint 的 `RELEASE` 在 SQLite 中等于 `COMMIT`，数据会真的落盘（见 §9）。

**M3 引擎单测清单**（纯核心，无数据库）：

| 文件 | 覆盖 |
|---|---|
| `test_compile.py` | 顺序/嵌套分支/并行组 → CompiledFlow；非法结构抛 `FlowInvalid` |
| `test_conditions.py` | 比较符、and/or、嵌套、字段缺失视为 false 且不抛错、else 兜底 |
| `test_expressions.py` | 四则 / 子表合计 / 日期差 / 拼接，与前后端共用测试向量一致 |
| `test_machine.py` | 全部合法迁移 + 全部非法迁移（含 REJECTED→APPROVED 禁止） |
| `test_router.py` | `plan_after_node` 分支命中/未命中/嵌套/并行展开/结束；`cancel_set_for_return` 的 5 类位置 |
| `test_permissions.py` | L0–L5 覆盖顺序、hidden→editable 反向点亮、条件覆盖、扩展字段、归档视角、子表列 |
| `test_aggregate.py` | all（全同意/一人驳回/一人退回）、any（首同意/先驳回）、sequential、并行组 JOINED/FAILED |

集成层（真实库）覆盖：提交派发、会签全同意与失败、或签取消其余、驳回→重提轮次、
退回不重走前序且数据不回滚、撤回守卫、终止、幂等重放与并发、机制 C 全链路。

---

## 9. 已知陷阱（踩过的坑，改代码前先读）

| 陷阱 | 现象 | 处理 |
|---|---|---|
| **`alembic.ini` 必须纯 ASCII** | alembic 用 `encoding="locale"`（中文 Windows 上是 GBK）读它，写 UTF-8 中文注释会在加载阶段直接 `UnicodeDecodeError` | 该文件是仓库唯一例外；原因在该文件头部与 `alembic/env.py` 中均有说明 |
| **pysqlite 不主动发 BEGIN** | `connection.begin()` 只是名义事务，最外层 `RELEASE SAVEPOINT` 等于 `COMMIT`，测试数据串场（表现为分页 total 数字翻倍） | `tests/conftest.py` 中设 `isolation_level=None` + 监听 `begin` 事件显式发 BEGIN |
| **`PageParams` 所在模块不能加 `from __future__ import annotations`** | 注解被推迟成字符串后，FastAPI 无法还原 `Annotated[int, Query(...)]`，请求处理时抛 `PydanticUserError` | `core/pagination.py` 不写该 import，文件头有说明 |
| **时间统一 naive UTC** | 依赖数据库默认值会让 SQLite（UTC）与 MySQL（会话时区）差 8 小时 | 见 D9；前端 `utils/datetime.ts` 补 `Z` 后再转本地 |
| **antd `Select` 不接受 `null`** | `v-model:value` 绑 `null` 时类型报错，且 `allow-clear` 回传的是 `undefined` | 查询条件字段一律用 `undefined` 而非 `null` |
| **antd `#bodyCell` 的 `record` 是 `Record<string, any>`** | 直接传给强类型函数会报 TS2345 | 模板里显式 `record as XxxItem` |
| **orm 对象直接序列化需 `from_attributes`** | `model_validate(orm_obj)` 抛 `model_type` 校验错误（GET /admin/audit-logs 曾因此 500） | DTO 加 `model_config = ConfigDict(from_attributes=True)`，或手工构造 |
| **`email-validator` 拒绝 `.local` 等保留 TLD** | `admin@flowform.local` 过不了 `EmailStr` 校验返回 422 | 示例与种子一律用 `@example.com` |
| **bcrypt 72 字节上限** | 超长密码在 bcrypt 4.x 直接抛 `ValueError`（登录变 500） | `security.py` 显式截断；`LoginRequest`/`UserCreate` 另有 `max_length=72` 保证不静默丢字符 |
| **Vite 7 需要 Node ≥ 22.12** | 本机 Node 22.4.1 装 Vite 7 会失败 | 锁 Vite 6 |

---

## 10. 本地运行

```bash
# 后端（首次）
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # Windows
cp .env.example .env
./.venv/Scripts/python.exe -m alembic upgrade head
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload          # :8000

# 前端（另开终端）
cd frontend
npm install
npm run dev                                                          # :5173

# 测试与检查
cd backend && ./.venv/Scripts/python.exe -m pytest -q
cd backend && ./.venv/Scripts/python.exe -m ruff check app tests
cd frontend && npm run typecheck
```

**切 MySQL**：`docker compose -f docker-compose.dev.yml up -d`，
把 `backend/.env` 的 `DATABASE_URL` 换成 `mysql+pymysql://...`，
再 `alembic upgrade head`。**不需要改任何模型或迁移代码** —— 这是 D1 的验收点。
