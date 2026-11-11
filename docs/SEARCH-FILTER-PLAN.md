# 按业务字段筛选实例列表（方案二：字段值索引表）

> 状态：设计/实施计划，**本轮不改代码**。等需要做「列表筛选」时按本文执行。
> 已确认范围：先只做实例列表/归档列表筛选，不做聚合统计；由表单设计者勾选「可检索」字段。
> 原则：JSON 仍是业务数据的唯一事实源；索引表是可重建的派生读模型。

## Context

- 表单定义在 `form_versions.schema` JSON，实例业务值在 `flow_instances.current_data` JSON；
  `code/title/status/initiator/dept/flow_version_id` 等元数据已是独立列。
- 当前实例/归档列表只支持 `title/code` 模糊、状态、流程模板、发起范围，无法按业务字段筛选。
- 直接拿 JSON 做 WHERE 的问题：SQLite/MySQL 的 JSON 语法、类型转换、数组包含不一致；
  动态路径没有通用索引，分页 COUNT 会扫全表。
- 生成列/每表单宽表需要按表单/字段做 DDL，违背项目「无 MySQL 专有 DDL / SQLite 可跑」的约束。
- 结论：新增**两张通用表**（可检索字段配置 + 字段值索引），一次迁移，不随表单数量做 DDL。

## 架构决策

1. **JSON 保留**：提交/审批仍写 `current_data`，索引表只读模型。
2. **配置表 `form_search_fields` 按 `(form_template_id, field_key)` 存**，不写进 `form_versions.schema`：
   - 已发布 schema 冻结；写进版本会导致存量实例必须重发流程才可检索；
   - field key 是跨版本稳定标识，模板级配置可覆盖历史版本和存量实例；
   - 同一 key 跨版本类型变化时在发布阶段阻断，避免索引语义混乱。
3. **索引表 `instance_field_values`**：每个实例 × 每个可检索字段写 1..N 行；
   多选一值一行；空值写 `empty` 行；字段在该版本不存在则不写行。
4. **同步点**：在引擎 `_start_round`（提交/重提）与 `act`（同意/驳回/退回/填写）的
   **同一事务**内重建该实例索引；草稿不索引；提供全量重建脚本。
5. **查询**：复用 `GET /instances`、`/instances/archive`、`/instances/archive/export`，
   增加 `filters` JSON 参数；不新增列表接口。所有条件 AND。
6. **安全**：字段必须在该模板的可检索配置白名单内；非管理员只开放 `scope=mine`
   且仅发起阶段可见字段；归档业务筛选仅管理员。复用现有 `build_query` 的可见性。

## 数据模型

### form_search_fields（配置表，`backend/app/models/form.py`）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PkMixin | |
| form_template_id | IntType FK form_templates.id cascade | |
| field_key | String(64) | 顶层字段 key |
| field_type | String(24) | 配置时的控件类型快照 |
| filter_kind | String(16) | text/number/date/time/datetime/bool/option/multi_option/user/user_multi/dept/dept_multi |
| label | String(128) | 标签快照 |
| options | JSON nullable | 各版本选项并集 |
| start_visible | Boolean | 「我发起的」是否允许筛选的保守标记 |
| sort | Integer | 面板排序 |
| indexed_at | DateTime nullable | 最近全量回填时间；新增字段为 NULL（待回填） |
| created_by / created_at / updated_at | | 审计 |

约束：`UniqueConstraint(form_template_id, field_key)`；`created_by` 索引。

### instance_field_values（值索引，`backend/app/models/instance.py`）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PkMixin | |
| instance_id | IntType FK flow_instances.id cascade | |
| field_key | String(64) | |
| value_kind | String(16) | text/number/datetime/bool/id/empty |
| value_text | String(512) nullable | 文本/选项/日期时间字符串，`casefold()` 后存 |
| value_num | Numeric(24,6) nullable | 数字、布尔 0/1、人员/部门 id |
| value_index | SmallInteger | 多选序号；单值/空值固定 0 |
| created_at | CreatedAtMixin | |

约束/索引：
- `UniqueConstraint(instance_id, field_key, value_index)`
- `(field_key, value_text, instance_id)`
- `(field_key, value_num, instance_id)`
- `(field_key, value_kind, instance_id)`（is_empty / is_not_empty）

适配：
- 只用现有 `IntType/String/Numeric/JSON/Boolean/DateTime`，无方言专有类型。
- 日期/时间按表单字符串写入，不依赖数据库时区。
- 文本统一 `casefold()`；查询值同样规范化。
- `value_text` 512：MySQL utf8mb4 下复合索引约 2312 字节，低于 3072 上限。
- 空值判定与后端一致：`None / "" / []`；存在 `empty` 行 = 字段适用但为空，
  完全无行 = 字段在该实例版本不存在或未回填。

## 可检索字段配置

允许：顶层、非展示、非附件/图片/子表的数据字段；`formula` 可配置，
`arithmetic/subtable_sum/date_diff` 视为 number，`concat` 视为 text。
排除：子表列、attachment、image、subtable、display。

校验（`backend/app/services/search_service.py`）：
- 每个模板最多 20 个可检索字段。
- 单选/多选/级联必须有选项。
- 同一 key 在模板各版本 `filter_kind` 必须一致，否则发布阻断 `SEARCH_FIELD_TYPE_CONFLICT`。
- `options` 取各版本并集，label 取最新版本。
- `start_visible` 取所有版本中「发起阶段可见且非 supplement 区」的保守结果。
- 新版本删除已配置字段：允许发布，但配置标记当前版本不存在，新实例不会索引该字段。

API（`backend/app/api/v1/form_templates.py`，DesignerUser）：
- `GET /form-templates/{id}/search-fields`：返回可配置字段列表、已配置状态、indexed_at。
- `PUT /form-templates/{id}/search-fields`：全量替换 field_keys；校验后 upsert；
  删除项同事务清理值索引；返回 added/removed/needs_backfill。
- 写审计 `AuditAction.UPDATE / AuditBizType.FORM_TEMPLATE`。

前端：
- `FieldPropertyPanel.vue`：顶层、允许类型字段显示「可检索」开关；说明「作用于该表单模板所有版本」。
- `FormDesignerView.vue`：加载/保存配置，头部「检索字段」抽屉。
- 新建 `SearchFieldPanel.vue`：字段列表、类型、已配置、批量勾选、待回填提示。
- `FormTemplateListView.vue`：行操作「检索字段」，已发布表单也能配置，无需新建版本。

## 索引同步与重建

新增 `backend/app/services/search_service.py`：
- `sync_instance_index(db, instance, form_schema=None, configs=None)`：
  草稿删除已有行并返回；无配置删行；按配置字段生成行；先 DELETE 再批量 INSERT；`flush()` 不 commit。
- 引擎接入（`backend/app/engine/service.py`）：
  - `_start_round`：`instance.current_data = values`、快照/派发完成后、commit 前同步；
  - `act`：各 `_handle_*` 完成后、commit 前同步。
  - 使用已有 `form_schema`，不再解析；引擎已按实例加锁，索引重建天然串行。
  - withdraw/abandon/terminate 只改状态，不重建；扩展字段 v1 不索引。
- 草稿（create/update draft）不索引；前端在筛选面板提示「仅已提交单据」。
- 配置删除：同事务删除该模板所有实例对应 `field_key` 的行。
- 配置新增：新提交立即有索引；存量实例由重建脚本回填，`indexed_at` 标记进度。
- 重建命令：`backend/app/scripts/rebuild_search_index.py`
  - `--all` / `--flow-template-id` / `--form-template-id` / `--batch-size 500` / `--dry-run`
  - 分批 commit，幂等；完成后更新 `indexed_at`。
- 迁移：`alembic/versions/0005_m_search_tables.py`（接 0004_m_auto_number），建两表与索引。

## 筛选 API

复用 `GET /instances`、`/instances/archive`、`/instances/archive/export`，新增可选
`filters`（JSON 字符串，AND 数组，最长 8192 字节，最多 10 个条件）：

```json
[{"field":"leaveType","op":"in","value":["annual"]},
 {"field":"days","op":"between","value":[3,10]}]
```

- 带 filters 时 `flow_template_id` 必填；否则 422 `FLOW_TEMPLATE_REQUIRED`。
- 解析失败 422 `FILTER_INVALID`；字段不在白名单 422；操作符/值不合法 422。
- 操作符按 filter_kind：text `contains/eq/is_empty/is_not_empty`；number `eq/gt/gte/lt/lte/between/...`；
  date/datetime/time 范围；bool `eq`；option `eq/in`；multi `has_any/has_all`；
  user/dept `eq/in`；multi user/dept `has_any/has_all`。
- 值规范化：文本 casefold；数字 Decimal；日期/时间 ISO 字符串；人员/部门正整数；
  between 两端校验；`has_all` 最多 50 值。
- SQL：每个条件构造相关 `EXISTS` 子查询（参数绑定，不拼接字段名）；
  `has_all` 用 `GROUP BY instance_id HAVING count(distinct value) = N`；
  `contains` 用 `value_text.contains(value, autoescape=True)`；保持现有排序。
- 白名单与权限：
  - `scope=mine`：非管理员只返回 `start_visible=True`，且按当前流程发起节点
    `resolve_field_permissions` 判定可见的字段；防止通过筛选推断隐藏补充字段。
  - `scope=archive`：仅管理员。
  - 非管理员 `related/all` + filters 拒绝 `FILTER_SCOPE_NOT_SUPPORTED`。
  - 列表仍走 `build_query` 原有 scope，不改变可见性。
- 新增元数据接口：
  - `GET /instances/search-fields?flow_template_id=&scope=mine|archive`
  - `GET /instances/my-flow-templates`（普通用户可调用，供工作台选择流程）
- 导出复用同一 `filters` 参数。

复用：`build_query`/`build_archive_query`（`instance_service.py`）、`PageParams/paginate/build_page`
（`core/pagination.py`）、`resolve_field_permissions`（`engine/permissions.py`）。

## 前端筛选 UI

- 新建 `frontend/src/components/instance/InstanceFilterBuilder.vue`：
  - 流程下拉 + 条件行（字段、操作符、值）；AND；最多 10 行；增加/删除/清空。
  - 控件复用 `FieldControl.vue`（text/number/date/time/datetime/switch/select/user/dept）与
    `OrgPickerControl.vue`（人员/部门树）；between 用两个值或 RangePicker。
  - 条件/字段/操作符变化时 `page=1`；序列化 `filters` JSON。
- 接入顺序：
  1. `InstanceArchiveView.vue`（管理员归档，已有流程下拉；导出使用同一 params）。
  2. `WorkbenchView.vue` 的 `mine` tab（普通用户用 `instanceApi.myFlowTemplates()`；
     `taskApi.mine` 增加 `flow_template_id`、`filters`）。
- 归档与 mine 的筛选条件放到 `route.query`，刷新可恢复；切换 tab/流程时清空。
- 待办/已办/抄送 v1 不接业务筛选。

## 实施阶段

### Phase 0：索引基础设施（后端）
1. 模型 `FormSearchField` / `InstanceFieldValue`，加入 models `__init__`。
2. 迁移 `0005_m_search_tables`（两表 + 索引 + 唯一约束）。
3. `search_service.py`：filter_kind 映射、规范化、build rows、sync/delete。
4. 引擎 `_start_round`、`act` commit 前同步。
5. `tests/test_search_index.py`。
6. 验收：提交/审批后 `instance_field_values` 有行；草稿无行。

### Phase 1：可检索配置与设计器
1. `schemas/search.py`、search_service 校验/保存/发布校验/复制模板配置。
2. `GET/PUT /form-templates/{id}/search-fields`。
3. `form_service.publish_version` 发布前校验、发布后刷新快照；`copy_template` 复制配置。
4. `scripts/rebuild_search_index.py`。
5. 前端 SearchFieldPanel、FieldPropertyPanel 开关、表单设计器/模板列表入口。
6. `tests/test_search_config.py`、`test_search_rebuild.py`。
7. 验收：勾选字段、发布冲突阻断、重建脚本 dry-run/正式回填。

### Phase 2：归档筛选
1. `search_service`：parse_filters、allowed_filter_fields、apply_business_filters、list_search_fields。
2. `build_query`/`build_archive_query` 增加 filters；列表/归档/导出路由增加 filters。
3. 新增 `GET /instances/search-fields`。
4. 前端类型/API、`InstanceFilterBuilder.vue`、`InstanceArchiveView.vue` 接入。
5. `tests/test_search_api.py`、前端筛选序列化测试。
6. 验收：归档按选项/数字/日期筛选；导出与列表一致；非法参数 422。

### Phase 3：我发起的 / URL 状态
1. `/tasks/mine` 增加 `flow_template_id`/filters；`build_mine_query` 委托 `build_query(scope=mine)`。
2. `GET /instances/my-flow-templates`。
3. `WorkbenchView.vue` mine 筛选 + URL query；归档 URL query。
4. 验收：非管理员 mine 可筛选；related/all 拒绝；隐藏字段不出现在元数据/请求中。

### Phase 4：硬化与性能
1. 在 MySQL 8 跑迁移与筛选；SQLite 同步验证。
2. 数据构造 10k 实例/8 字段，记录 p95：单条件 ≤300ms、三条件 ≤500ms（MySQL）；
   全量重建 ≤2 分钟（batch 500）；EXPLAIN 命中索引。
3. 安全复查：白名单、scope、autoescape、条件/值数量、隐藏字段。
4. 文档：`docs/SEARCH-FILTER.md` 记录表结构、操作符、权限、重建命令。
5. 可选：小模板（≤2000 实例）配置保存时同步回填。

## 测试与验收

- 后端：索引行类型/多选/空值/公式；提交/act/重提更新；草稿不索引；配置校验；
  删除配置清理；筛选各操作符；scope/隐藏字段；导出；重建幂等；迁移。
- 前端：filters 序列化/反序列化、默认操作符/字段切换清理、URL 恢复、组件渲染。
- 端到端：设计器勾选 → 发布表单/流程 → 提交 → 审批改字段 → 归档筛选/导出命中。
- 全量：`bash scripts/check.sh`；MySQL/SQLite 各跑一轮。

## 风险与后续

- 字段 key 改名/复用 → 新字段语义；跨版本类型冲突发布阻断。
- 存量未回填 → `indexed_at` + 重建脚本 + 面板提示；上线必须回填一次。
- 草稿不索引 → 文案说明；需要时再在 draft 写路径同步（接受写放大）。
- `contains` 无索引 → 先靠 scope/template/status 缩小候选；文本超 512 字符只索引前缀。
- 扩展字段/子表 v1 不支持；后续分别设计。
- 自动统计/报表/全文检索不在此方案：出现 GROUP BY/SUM/趋势、10 万级实例或 p95 超标时，
  优先上独立报表读模型/数仓或搜索引擎，不在本索引表上堆聚合。

## 关键文件

- 新增：`backend/app/services/search_service.py`、`backend/app/schemas/search.py`、
  `backend/app/scripts/rebuild_search_index.py`、`backend/alembic/versions/0005_m_search_tables.py`、
  `frontend/src/components/form-designer/SearchFieldPanel.vue`、
  `frontend/src/components/instance/InstanceFilterBuilder.vue`、
  `backend/tests/test_search_index.py`、`test_search_api.py`、`test_search_config.py`、`test_search_rebuild.py`
- 修改：`backend/app/models/form.py`、`models/instance.py`、`models/__init__.py`、
  `engine/service.py`、`services/instance_service.py`、`services/form_service.py`、
  `services/task_service.py`、`api/v1/instances.py`、`api/v1/form_templates.py`、`api/v1/tasks.py`、
  `frontend/src/views/admin/InstanceArchiveView.vue`、`views/WorkbenchView.vue`、
  `components/form-designer/FieldPropertyPanel.vue`、`views/admin/form/FormDesignerView.vue`、
  `views/admin/form/FormTemplateListView.vue`、`types/form.ts`、`types/instance.ts`、
  `api/modules/form.ts`、`api/modules/instance.ts`
