# FlowForm 三期设计（V3）

> 配套：`PRD-lowcode-form-approval.md`、`TECH-DESIGN.md`、`PHASE2-DESIGN.md`。
> 本文是三期的范围、模块边界与里程碑依据；具体实现随里程碑增量修订。
> **当前状态：M11–M16 全部完成。**

---

## 0. 三期目标与边界

### 0.1 主线

三期解决的问题从「能不能配出来」转向「日常好不好用」：

1. **首页信息架构**：替换当前只有欢迎语和里程碑进度的占位首页，普通用户看个人工作台，管理员/设计者额外看全局概览。
2. **共享表格**：嵌入式 Univer 在线 Excel，支持多个工作簿、多个 sheet、自由单元格与公式，多人近实时协同填写。
3. **实例台账检索**：按 `docs/SEARCH-FILTER-PLAN.md` 实施，让归档/我发起的列表能按业务字段筛选并导出。
4. **转办与委托**：补上日常审批中最常见的两个流转能力，减少「人不在就没法推进」的阻塞。
5. **AI 辅助配置**：自然语言生成表单 schema 与流程定义草稿，在设计器里预览、校验后应用，不自动发布。

### 0.2 里程碑顺序

按「价值优先」推进：首页和共享表格先解决「没信息、没地方填」，再做台账检索和流转能力，AI 因依赖网络例外审批与模型效果验证，放在最后落地。

| 里程碑 | 主题 | 交付 | 验收 |
|---|---|---|---|
| **M11** | 首页 | 按角色展示个人工作台 / 管理员概览，替换占位页 | 登录后第一屏能看到待办、我发起的、常用流程；管理员/设计者能看到全局概览 |
| **M12** | 共享表格 | Univer 在线 Excel：多工作簿、多 sheet、近实时协同、导出 Excel | 多人同时填写不同区域；版本冲突可加载最新或覆盖；导出 xlsx 可打开 |
| **M13** | 实例台账检索 | 按 `SEARCH-FILTER-PLAN.md` 实现业务字段筛选与导出 | 归档列表可按选项/数字/日期筛选，导出与列表一致 |
| **M14** | 转办与委托 | 待办转办、时段委托代理，全链路留痕与通知 | 转办后目标人可处理且原处理人可见；委托期内新任务派给被委托人 |
| **M15** | AI 辅助配置 | 自然语言生成表单 schema / 流程定义草稿 | 生成结果通过 schema 与发布校验，可预览、可修改、不自动保存发布 |
| **M16** | 收尾 | 审计与文档、全量回归、真机验收 | `check.sh` 全绿；五条端到端场景跑通 |

### 0.3 三期明确不做

- 催办、超时提醒、自动升级；
- 加签（前加签/后加签）；
- 部门级数据权限（实例可见范围仍按「发起人 + 历任/现任处理人 + 抄送人 + 管理员」）；
- 工作量自动统计（不从审批实例汇总工作量）；
- 表格公式、合并单元格、条件格式、多 sheet 关联计算；
- 实时协同（WebSocket/CRDT）；三期用轮询 + 乐观锁满足内网团队规模；
- 外部 SaaS 表格（腾讯文档/飞书/企业微信文档）；
- 多租户、BPMN 全标准、复杂 BI 与数据大屏；
- 移动端专项优化（管理端与协作表格保证可用即可）。

---

## 1. M11：首页

### 1.1 目标

首页当前仍是 M1 占位页，展示的是里程碑进度而非工作信息。M11 把它改成真正的入口页：**打开系统就知道今天要做什么、从哪里发起、最近发生了什么**。

### 1.2 页面结构

**普通用户（所有角色）**

| 区块 | 内容 |
|---|---|
| 欢迎区 | 问候语、当前日期、部门/角色标签 |
| 数据卡片 | 待办数、抄送未读、我发起的进行中、本月我发起的已完成 |
| 待办预览 | 最近 5 条待办：标题、单号、当前节点、到达时间，点击直达详情 |
| 我发起的 | 最近 5 条：标题、状态、当前节点、更新时间 |
| 常用流程 | 可发起流程按「本人最近发起次数」排序，最多 6 个，点击进入发起页 |

**管理员/设计者额外区块**

| 区块 | 内容 |
|---|---|
| 全局概览 | 运行中实例数、今日提交数、本周完成数、待办积压数 |
| 流程分布 | 运行中实例按流程模板聚合的 Top 5（名称 + 数量） |
| 管理入口 | 表单模板、流程模板、实例台账、共享表格的快捷入口 |

不引入图表库：首期用 Ant Design 的 `Statistic`、进度条和列表，避免为几张卡片增加构建体积。

### 1.3 数据接口

新增 `GET /api/v1/dashboard/overview`，一次返回首页所需数据，避免首屏发 5–6 个请求：

```jsonc
{
  "personal": {
    "todo": 3,
    "cc_unread": 1,
    "mine_running": 2,
    "mine_finished_this_month": 5
  },
  "todos": [
    { "assignment_id": 88, "instance_id": 12, "title": "出差申请",
      "code": "FLOW20261111-0001", "node_name": "部门审批", "arrived_at": "..." }
  ],
  "my_instances": [
    { "instance_id": 12, "title": "出差申请", "status": "RUNNING",
      "current_node_name": "部门审批", "updated_at": "..." }
  ],
  "quick_flows": [
    { "flow_template_id": 3, "name": "请假申请", "icon": null }
  ],
  "work_stats": [
    { "sheet_id": 1, "name": "部门月度工作量", "updated_at": "..." }
  ],
  "admin": {
    "running": 12,
    "submitted_today": 4,
    "finished_this_week": 9,
    "pending_backlog": 18,
    "by_flow": [{ "flow_template_id": 3, "name": "请假申请", "count": 5 }]
  }
}
```

- `admin` 字段仅管理员/设计者返回，普通用户为 `null`。
- 复用现有 `task_service.summary` 的统计口径；`by_flow` 用一条 GROUP BY 查询，不逐流程循环。
- 常用流程复用发起中心的可发起过滤逻辑，再按当前用户最近发起次数排序。
- 前端沿用 10 秒轮询刷新角标与待办预览；其余区块进入页面时加载一次。

### 1.4 实现边界

- 不改动实例可见性规则；
- 不改动工作台四个 tab 的数据口径；
- 首页所有卡片只读，写操作仍在对应页面完成。

### 1.5 验收

- 普通用户登录后第一屏能看到待办、我发起的、常用流程，无待办时显示空状态而不是空白；
- 管理员额外看到全局概览和流程分布；
- 点击待办/实例/流程分别落到详情页、发起页；
- 首页接口只发一次请求，刷新不闪烁；
- 原有工作台、发起中心测试全绿。

### 1.6 M11 实现状态

已完成（提交在 `feat3` 分支）：

- 后端 `GET /api/v1/dashboard/overview` 一次返回个人计数、待办预览、我发起的、
  常用流程与管理概览；今日/本周/本月按 `app_timezone`（默认 Asia/Shanghai）计算。
- 首页拆分为 `StatTiles`、`TodoPreviewList`、`InstancePreviewList`、`QuickFlowGrid`、
  `AdminOverviewPanel` 五个组件；普通用户看个人工作台，管理员/设计者额外看全局概览。
- 测试：`backend/tests/test_dashboard.py` 4 项；前端首页角色断言 2 项。
- 全量校验：429 pytest + 124 vitest + ruff / vue-tsc / vite build 全绿。

---

## 2. M12：共享表格（在线 Excel）

### 2.1 定位

**在线 Excel 工作簿**，不是固定列台账。用户可以新建多个工作簿，每个工作簿包含多个
sheet，自由编辑单元格、公式、格式、合并单元格。

协同采用**近实时**模型：编辑自动保存，其他客户端每 5 秒同步一次；多人可以同时填写
不同区域，同一版本冲突时提示「加载最新」或「覆盖保存」。不做实时协作光标。

### 2.2 技术选型

- 编辑器：**Univer**（Apache-2.0 核心，`@univerjs/presets` + `@univerjs/preset-sheets-core`）。
- 中文界面：`@univerjs/preset-sheets-core/locales/zh-CN`。
- 导出 Excel：SheetJS（`xlsx`）从 Univer 快照生成，支持值、公式、合并单元格、
  行高列宽；不导出颜色/字体等样式。
- 首版**不做 xlsx 导入**（Univer 的导入/导出在 Pro 包；后续需要时再接 SheetJS 转换
  或 Univer Pro）。

### 2.3 数据模型（迁移 `0008_m_spreadsheets`）

**`spreadsheet_workbooks`**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PkMixin | |
| name | String(128) | 工作簿名称 |
| description | String(512) nullable | 说明 |
| snapshot | JSON nullable | Univer `IWorkbookData` 完整快照 |
| version | Integer | 乐观锁版本，每次保存 +1 |
| viewer_scope | JSON nullable | `{"all": bool, "roles": [], "depts": [], "users": []}` |
| editor_scope | JSON nullable | 同上；创建者和管理员始终可编辑 |
| status | String(16) | ACTIVE |
| created_by / updated_by | IntType | |
| created_at / updated_at | | |

范围语义：

- `all=true`：全体登录用户；
- 列表命中任一角色/部门/人员即可；
- `viewer_scope=null` 或空对象：仅创建者和管理员可见；
- `editor_scope=null` 或空对象：仅创建者和管理员可编辑；
- 创建者和管理员始终可见、可编辑。

快照上限 5MB；超过时提示拆分工作簿。

### 2.4 协同与冲突

- 编辑器监听 Univer `CommandExecuted`，停止操作 1.5 秒后自动保存整份快照。
- 保存请求携带本地 `version`；服务端不一致返回 `409 SPREADSHEET_VERSION_CONFLICT`。
- 冲突时页面提示「加载最新」或「覆盖保存」：
  - 加载最新：丢弃本地改动，重新创建 Univer 工作簿；
  - 覆盖保存：先取服务端当前版本，再用本地快照覆盖。
- 每 5 秒轮询 `GET /{id}/state?known_version=`；版本变化且本地无未保存改动时，
  自动重建工作簿到最新快照；本地有改动时提示冲突。
- 不做 OT/CRDT、不做逐单元格锁；内网团队规模下满足「多人协同填写」。

### 2.5 权限

- 所有登录用户都可以新建工作簿。
- 创建者可以修改名称/说明、配置查看与编辑范围、删除工作簿。
- 管理员可以管理全部工作簿。
- 编辑者可以编辑单元格并保存，但不能修改共享范围或删除。
- 只读用户打开工作簿时 `setEditable(false)`。

### 2.6 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/spreadsheet-workbooks` | 我可见的工作簿列表 |
| POST | `/spreadsheet-workbooks` | 新建（所有登录用户） |
| GET | `/spreadsheet-workbooks/{id}` | 详情 + 快照 |
| PUT | `/spreadsheet-workbooks/{id}` | 修改名称/说明/共享范围（创建者/管理员） |
| POST | `/spreadsheet-workbooks/{id}/save` | 保存快照，校验 version |
| GET | `/spreadsheet-workbooks/{id}/state` | 轮询最新版本/快照 |
| DELETE | `/spreadsheet-workbooks/{id}` | 删除（创建者/管理员） |

### 2.7 前端

- 新增 `views/SpreadsheetsView.vue`（列表、新建、共享设置、删除）。
- 新增 `views/SpreadsheetWorkbookView.vue`（Univer 编辑器、自动保存、轮询、冲突处理、导出）。
- 新增 `components/spreadsheet/UniverSheet.vue`：只负责挂载/销毁 Univer、加载快照、
  发出变更事件、暴露 `getSnapshot()`；Univer 实例存在普通变量里，不放进响应式 ref。
- 新增 `utils/spreadsheetExport.ts`：快照 → xlsx。
- 菜单项「共享表格」替换原「工作量统计」；原结构化模块不再从菜单/首页进入。

### 2.8 验收

- 任一用户可新建工作簿，打开后能编辑单元格、公式、多个 sheet；
- 编辑后 1.5 秒自动保存，刷新页面内容还在；
- 两个账号打开同一工作簿：一方保存后，另一方 5 秒内看到最新内容；
- 双方都改同一版本时，后保存者收到冲突提示，可加载最新或覆盖；
- 只读用户不能编辑；
- 能导出 `.xlsx` 并用 Excel 打开，值/公式/合并单元格正确。

### 2.9 M12 实现状态

已完成：

- 后端：`spreadsheet_workbooks` 表（迁移 `0008_m_spreadsheets`）、权限、
  快照保存乐观锁、状态轮询接口；`backend/tests/test_spreadsheets.py` 6 项通过。
- 前端：Univer 1.4.0 编辑器、工作簿列表/共享设置、自动保存 + 5 秒轮询、
  冲突加载/覆盖、SheetJS 导出。
- 全量校验：450 pytest + 128 vitest + ruff / vue-tsc / vite build 全绿。
- 构建提示：Univer 编辑器单独懒加载，chunk 约 7.2MB（gzip 1.95MB），只进入
  工作簿页面时加载；后续可再做 manualChunks 优化。

---

## 3. M13：实例台账检索

### 3.1 范围

按 [`docs/SEARCH-FILTER-PLAN.md`](SEARCH-FILTER-PLAN.md) 实施，不在本文重复表结构与操作符细节。范围包括：

- 表单设计者勾选「可检索」字段；
- 提交/审批时同步字段值索引；
- 归档列表、「我发起的」按业务字段筛选；
- 导出复用同一筛选条件；
- 存量实例重建索引脚本。

### 3.2 与二期计划的差异

`SEARCH-FILTER-PLAN.md` 中规划的迁移号是 `0005_m_search_tables`；三期实际迁移顺序为：

- `0005_m_work_stats`（早期结构化统计，已弃用）
- `0006_m_search_tables`（M13）
- `0007_m_transfer_delegation`（M14）
- `0008_m_spreadsheets`（M12 共享表格）

其余设计与验收以 `SEARCH-FILTER-PLAN.md` 为准。

### 3.3 实施阶段

| 阶段 | 内容 | 交付 |
|---|---|---|
| Phase 0 | 索引表、模型、迁移、引擎同步 | 提交/审批后有索引行，草稿无 |
| Phase 1 | 可检索字段配置、设计器入口、重建脚本 | 勾选字段、发布校验、全量回填 |
| Phase 2 | 归档筛选 API 与 UI、导出 | 管理员归档可按业务字段筛选 |
| Phase 3 | 「我发起的」筛选与 URL 状态 | 普通用户可筛选自己的单据 |
| Phase 4 | MySQL/SQLite 验证、性能与安全复查、文档 | p95 与索引命中达标 |

### 3.4 前端接入

- 新建 `components/instance/InstanceFilterBuilder.vue`；
- 接入 `InstanceArchiveView.vue` 与 `WorkbenchView.vue` 的 `mine` 标签；
- 筛选条件写入 `route.query`，刷新可恢复；切换标签或流程时清空；
- 待办/已办/抄送三期不接业务筛选。

### 3.5 验收

- 设计者在表单设计器勾选 3 个可检索字段并发布；
- 新提交的实例可按选项、数字区间、日期范围筛选；
- 归档列表导出结果与筛选结果一致；
- 删除/停用可检索字段的配置后，列表不再提供该筛选项；
- 存量实例重建脚本支持 `--dry-run`，重复执行幂等；
- 非管理员请求归档筛选被拒绝，隐藏字段不能通过筛选推断。

### 3.6 M13 实现状态

已完成（提交在 `feat3` 分支）：

- 后端：`form_search_fields` / `instance_field_values` 两张表（迁移
  `0006_m_search_tables`）；可检索字段配置、发布时类型冲突阻断、复制模板带配置；
  引擎在提交与审批的同一事务内重建索引；筛选 API 覆盖归档、我发起的与导出；
  重建脚本 `python -m app.scripts.rebuild_search_index`，页面「检索字段」弹窗也提供
  「重建索引」按钮（先保存配置，再重建该表单下全部已提交实例）。
- 前端：表单设计器/模板列表的「检索字段」配置、归档与「我发起的」业务字段筛选器。
- 修复：筛选接口按**流程模板 id** 解析对应的表单模板后再取配置（两者 id 通常不相等）。
- 测试：`backend/tests/test_search.py` 6 项，覆盖配置、筛选、类型冲突、复制、
  重建接口与流程/表单 id 不相等的情况。
- 全量校验：452 pytest + 128 vitest + ruff / vue-tsc / vite build 全绿。

---

## 4. M14：转办与委托

### 4.1 转办

**语义**：当前处理人把自己的一条待办转给另一个人处理，节点、权限、审批语义不变，只换处理人。

规则：

- 仅 `PENDING` 状态的指派可转办；已处理、已取消、抄送不可转办。
- 仅指派人本人可发起；管理员可代为转办。
- 目标人必须是启用状态用户，且不能是同一任务同序号已有待办的人（会签组内撞重直接拒绝）。
- 转办原因必填，写入动作记录与审计。
- 原指派置为 `CANCELLED`，`cancel_reason=TRANSFERRED`；为目标人新建同 `task_id`、同 `seq` 的待办。
- 目标人获得该节点原有字段权限；原处理人仍保留实例可见性（历史参与人）。
- 会签/或签/并行组：只替换该成员的人，不改变组结构与聚合规则。

**入口**：工作台待办行、实例详情处理区、管理员实例管理页。

### 4.2 委托

**语义**：用户在指定时段内，把自己的审批任务交给另一个人代理。

规则：

- 委托人本人创建；管理员可查看和强制结束。
- 必填：被委托人、开始时间、结束时间、委托原因；可选：限定流程模板（空=全部流程）。
- 被委托人不能是委托人本人；必须是启用用户。
- 同一委托人同一时段只允许一条生效委托（不支持按流程拆成多条并行委托）；`flow_template_ids` 用于限定这条委托覆盖哪些流程。
- 委托只影响**新派发**的任务：派发时若处理人有生效委托，直接把待办派给被委托人，并记录来源。
- 已存在的待办不自动转交；需要时由委托人逐条转办。
- 被委托人已在该任务上有待办时，跳过委托、按原处理人派发，并通知委托人「委托未生效」。
- 委托是否生效按 `start_at <= 当前时间 < end_at` 判断，到期自动失效，不需要定时任务；已派出的待办不回退。

### 4.3 数据模型（迁移 `0007_m_transfer_delegation`）

**`task_assignments` 新增列**

| 字段 | 类型 | 说明 |
|---|---|---|
| origin_user_id | IntType nullable | 转办/委托来源用户 |
| origin_kind | String(16) nullable | TRANSFER / DELEGATION |
| origin_reason | String(512) nullable | 转办/委托原因快照 |

**`delegations` 新表**

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PkMixin | |
| delegator_id | IntType FK users.id | 委托人 |
| delegatee_id | IntType FK users.id | 被委托人 |
| start_at / end_at | DateTime | 生效区间 |
| flow_template_ids | JSON nullable | 限定流程；空=全部 |
| reason | String(512) | 委托原因 |
| status | String(16) | ACTIVE / CANCELLED；是否到期按时间判断，不落过期状态 |
| created_by / created_at / updated_at | | |

索引：`(delegator_id, status)`、`(delegatee_id, status)`。

### 4.4 引擎接入

- 派发任务时（创建 `TaskAssignment` 的统一入口）解析生效委托：
  - 命中且被委托人不在同一任务已有待办中 → 新建指派给被委托人，`origin_user_id=委托人`、`origin_kind=DELEGATION`；
  - 未命中或撞重 → 按原处理人派发。
- 转办是独立动作：取消原指派 + 新建指派 + 写 `InstanceAction(action=TRANSFER)`；不推进令牌、不改节点状态。
- 实例可见性查询扩展：`user_id == 我 OR origin_user_id == 我`，保证委托人和转办原处理人仍能查看详情。
- 待办/已办列表：转办后原处理人的待办消失，在「已办」中显示「已转办」；被委托人按正常待办处理。

### 4.5 通知与审计

新增通知类型：

- `TASK_TRANSFERRED`：通知被转办人（有新待办）和原处理人（已转出）；
- `TASK_DELEGATED`：通知被委托人（代理待办）和委托人（委托生效/未生效）。

转办写 `InstanceAction(action=TRANSFER)` 并进入实例时间线；委托属于用户配置变更，只写操作审计（`AuditAction.DELEGATE`），不进入实例时间线。两处新增标签都要同步后端 `core/constants.py` 与前端 `stores/app.ts` 的映射。

### 4.6 权限与边界

- 转办不改变节点审批人规则，只改变当前指派；
- 委托不改变流程定义与权限矩阵；
- 管理员转办/终止委托均写审计；
- 填写节点同样适用转办；委托对审批/填写节点生效，抄送不参与转办与委托。

### 4.7 验收

- A 转办给 B：A 的待办消失、B 出现待办并可同意；实例详情显示「A 转办给 B」及原因；
- 目标人已在同任务有指派时转办被拒绝，提示明确；
- 会签组中一人转办后，组仍按原聚合规则继续；
- 委托期内新任务派给被委托人，实例详情显示代理关系；委托人仍能查看详情；
- 委托重叠、被委托人/委托人相同、过期时间早于开始时间均被拒绝；
- 委托到期后新任务回到委托人；
- 转办记录在通知、审计和实例时间线可见；委托在通知与操作审计可见，代理关系体现在待办和实例详情中。

---

## 5. M15：AI 辅助配置

### 5.1 能力边界

三期只做**配置生成**：

- 自然语言描述业务 → 生成表单 schema（分区、字段、类型、选项、必填、校验）；
- 自然语言 + 选定表单 → 生成流程定义（节点、条件分支、抄送、审批人占位）；
- 生成结果是设计器草稿，必须人工预览、修改并通过现有校验后才能保存/发布。

不做智能填单、审批摘要、风险提示、自动修改现有配置。

### 5.2 架构

```
前端设计器「AI 生成」弹窗
        ↓ POST /ai/form-schema | /ai/flow-definition
后端 ai_service（OpenAI 兼容适配层）
        ↓ 只发送业务描述 + schema 约束
云端模型 API（经网络例外审批的地址）
        ↓ 返回 JSON
Pydantic 校验（FormSchema / FlowDefinition）
        ↓ 失败则带错误信息自动修复重试 1 次
返回草稿给前端预览
```

- 新增 `backend/app/services/ai_service.py` 与 `backend/app/api/v1/ai.py`；
- 配置走环境变量：`AI_ENABLED`、`AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL`、`AI_TIMEOUT_SECONDS`、`AI_MAX_TOKENS`；
- `AI_ENABLED=false` 时接口返回 404 `AI_DISABLED`，前端不显示入口；
- 仅管理员/设计者可用（`DesignerUser`）。

### 5.3 表单生成

- 输入：业务描述（必填，≤2000 字）、可选的控件偏好（如「不要子表」）；
- 提示词包含：`FormSchema` 的字段类型清单、展示控件约束、校验规则、两个精简示例；
- 输出：完整 `FormSchema` JSON；
- 后端校验：schema 结构、字段 key 唯一、选项/公式/条件引用合法、展示控件约束；
- 校验失败时把错误摘要回传模型修复一次；仍失败则返回 422 `AI_OUTPUT_INVALID`；
- 前端在表单设计器中展示分区/字段预览，用户点「应用」后进入草稿（覆盖或追加需二次确认）。

### 5.4 流程生成

- 输入：业务描述 + 已选表单 schema；
- 提示词包含：`FlowDefinition` 的节点类型、审批人来源类型、条件结构、字段 key 清单；
- 审批人只允许生成**占位配置**：角色/部门主管/发起人指定/指定人员；模型不得编造具体用户 id，人员节点统一留空由用户选择；
- 输出：完整 `FlowDefinition` JSON；
- 后端复用现有 `compile_flow` / `validate` 做静态校验；错误同样修复重试一次；
- 前端在流程设计器中预览节点清单/画布，点「应用」进入草稿；
- 发布仍走现有校验，审批人未配置时无法发布。

### 5.5 安全与审计

- 只发送业务描述与 schema 结构，不发送实例数据、附件、人员真实姓名、组织架构明细；
- 前端不直接调用模型，密钥只在后端环境变量；
- 出网地址由后端配置固定，不接受前端传入 `base_url`；
- 每用户限流：默认 20 次/小时，按 `audit_logs` 统计；
- 审计记录：操作人、生成类型、模型名、耗时、token 数、prompt 哈希、成功/失败与错误码；默认不落原始 prompt；
- 功能可整体关闭；关闭后历史生成记录仍可查。

### 5.6 验收

- 输入「做一个出差申请，包含目的地、起止日期、交通方式、预计费用，部门经理和财务审批」，能生成可预览的表单与流程草稿；
- 生成结果通过 schema 校验与发布校验；审批人占位未配置时发布被拦截；
- 模型返回非法 JSON 时自动重试一次，仍失败给出明确错误，不污染现有草稿；
- 关闭 AI 开关后入口消失、接口不可用；
- 审计能查到每次生成的模型、耗时与 token，不包含业务数据原文；
- 自动化测试用 mock provider，不在 CI 调真实模型。

### 5.7 M15 实现状态

已完成（提交在 `feat3` 分支）：

- 后端：`services/ai_service.py` + `api/v1/ai.py`，OpenAI 兼容协议；表单生成走
  `FormSchema` + 语义校验，流程生成走 `FlowDefinition` + 引擎静态校验；
  校验失败自动修复重试一次；每用户每小时限流；审计只记录 prompt 哈希、模型、
  耗时与 token，不落业务原文；默认关闭，关闭时接口 404 `AI_DISABLED`。
- 前端：表单/流程设计器的「AI 生成」弹窗，展示 JSON 预览后手动应用并二次确认；
  不自动保存、不自动发布。
- 配置：`AI_ENABLED` / `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL` 等环境变量。
- 测试：`backend/tests/test_ai_generate.py` 7 项（含修复重试、限流、关闭）。
- 全量校验：450 pytest + 128 vitest + ruff / vue-tsc / vite build 全绿。

---

## 6. M16：收尾

- 新增通知类型、审计动作的前端标签同步；
- 文档：更新 `README.md`、`TECH-DESIGN.md` 里程碑状态，补 `docs/PHASE3-DESIGN.md` 的实现状态；
- 端到端场景：
  1. 普通用户首页 → 待办 → 处理 → 首页数据更新；
  2. 管理员建工作量表 → 导入 Excel → 两人协作编辑 → 导出；
  3. 设计者配置可检索字段 → 发起审批 → 归档筛选 → 导出；
  4. 转办/委托各走一遍；
  5. AI 生成表单+流程 → 修改审批人 → 发布 → 发起。
- `bash scripts/check.sh` 全量五项通过；
- 真机验收首页、协作表格、转办/委托、AI 生成。

---

## 7. 兼容与迁移

| 里程碑 | 迁移 | 影响 |
|---|---|---|
| M11 首页 | 无 | 纯读接口与前端页面 |
| M12 共享表格 | `0008_m_spreadsheets` | 新增 1 张表；旧 `0005_m_work_stats` 保留但不再使用 |
| M13 实例台账检索 | `0006_m_search_tables` | 新增 2 张表；见 `SEARCH-FILTER-PLAN.md` |
| M14 转办与委托 | `0007_m_transfer_delegation` | 1 张新表 + `task_assignments` 3 列 |
| M15 AI | 无 | 配置与审计 |

- 所有新增列可空；历史任务与实例原样可读；
- 不改变现有流程定义、表单 schema、快照与导出格式；
- 共享表格是独立数据，不进入实例快照与归档导出；
- 三期不升级 `model_version`。

---

## 8. 测试策略

| 层 | 内容 |
|---|---|
| 纯函数 | 共享表格快照/权限规则、转办/委托规则、AI 输出校验 |
| 后端集成 | 首页聚合接口、工作簿版本冲突、委托派发、转办留痕、AI mock 生成 |
| 前端组件 | 首页角色区块、Univer 工作簿列表/编辑器挂载、冲突提示、筛选器、转办/委托弹窗、AI 预览 |
| 端到端 | 见 M16 五条场景 |
| 安全 | 台账可见/可编辑范围、转办目标校验、委托重叠、AI 出网内容与限流 |
| 收尾 | `bash scripts/check.sh` 全量五项 |

新增测试文件建议：

- `backend/tests/test_dashboard.py`
- `backend/tests/test_work_stats.py`
- `backend/tests/test_work_stats_import.py`
- `backend/tests/test_search_*`（按 SEARCH-FILTER-PLAN）
- `backend/tests/test_transfer_delegation.py`
- `backend/tests/test_ai_generate.py`
- `frontend/src/__tests__/` 下补首页、协作表格、筛选器、转办/委托、AI 预览用例

---

## 9. 风险与应对

| 风险 | 应对 |
|---|---|
| 协作表格同格冲突导致数据覆盖 | 行级 `version` 乐观锁 + 冲突提示 + 只刷新冲突行；不做静默覆盖 |
| 轮询造成频繁请求 | 5 秒增量拉取，只返回 `updated_at` 之后的行；单表 ≤2000 行 |
| Excel 导入格式五花八门 | 固定列定义 + 表头映射 + 前 20 行预览 + 整批事务回滚；错误逐行提示 |
| 转办/委托破坏会签、或签语义 | 只替换/新增指派，不改令牌与聚合；撞重直接拒绝并补测试 |
| 委托范围与可见性不一致 | 可见性查询纳入 `origin_user_id`；委托人、原处理人保留查看权 |
| AI 输出不可用或幻觉 | schema 校验 + 一次修复重试 + 预览确认 + 不自动保存发布 |
| AI 数据外发风险 | 只发描述与 schema 结构；后端固定出网地址；审计与限流；可整体关闭 |
| 台账检索性能 | 按 `SEARCH-FILTER-PLAN.md` 的索引表与重建脚本实施；MySQL/SQLite 双验证 |
| 首页聚合接口变慢 | 一次请求内批量查询；统计口径复用现有索引列；必要时加短缓存 |

---

## 10. 完成定义（DoD）

### M11 首页

- [ ] 普通用户/管理员/设计者首页区块按角色展示；
- [ ] `GET /dashboard/overview` 一次返回所需数据；
- [ ] 所有卡片能跳到对应页面，空状态完整；
- [ ] 首页渲染测试与后端聚合测试通过。

### M12 共享表格

- [ ] 任意用户可新建多个工作簿，每个工作簿支持多个 sheet；
- [ ] Univer 编辑器可编辑单元格、公式、格式；
- [ ] 自动保存 + 5 秒轮询；版本冲突可加载最新或覆盖；
- [ ] 创建者/管理员可配置查看与编辑范围；
- [ ] 可导出 xlsx，值和公式正确；
- [ ] 后端/前端测试通过。

### M13 实例台账检索

- [ ] `SEARCH-FILTER-PLAN.md` Phase 0–4 全部完成；
- [ ] 归档与我发起的筛选、导出、URL 状态可用；
- [ ] 索引重建脚本幂等，MySQL/SQLite 验证通过；
- [ ] 安全与性能验收达标。

### M14 转办与委托

- [ ] 转办、委托的 API、引擎接入、通知、审计、时间线全部可用；
- [ ] 会签/或签/填写节点场景测试通过；
- [ ] 委托重叠、撞重、过期等边界有测试覆盖。

### M15 AI 辅助配置

- [ ] 表单/流程生成接口、预览、应用草稿可用；
- [ ] 输出校验与一次修复重试可用；
- [ ] 开关、限流、审计、无业务数据外发；
- [ ] mock provider 测试通过。

### M16 收尾

- [ ] 文档与演示更新；
- [ ] 五条端到端场景通过；
- [ ] `bash scripts/check.sh` 全绿；
- [ ] 用户真机验收完成。
