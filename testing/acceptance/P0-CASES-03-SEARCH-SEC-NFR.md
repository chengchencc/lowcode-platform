# P0 验收用例 03：检索、归档、首页、安全与并发 + 非功能检查

> **状态：DRAFT** — 待产品负责人确认“期望结果”与文末“需求待确认项”后再冻结；未确认项不得由实现方自行补规则。
>
> **生成方式**：Spec-only。仅依据 `testing/.runtime/spec-pack/` 中的需求/设计文档与接口契约设计；未读取 `backend/`、`frontend/`、`testing/e2e/`、`scripts/` 或任何源码/测试代码。
>
> **生成依据（Spec Pack）**：
> - `docs/TEMPLATE.md`（输出格式）
> - `docs/TEST-PLAN.md` §6、§10（P0 场景清单、非功能检查）
> - `docs/PRD-lowcode-form-approval.md` §7、§8、F6/F8
> - `docs/PHASE3-DESIGN.md` M11 首页、M13 检索、§10 DoD
> - `docs/SEARCH-FILTER-PLAN.md`
> - `docs/TECH-DESIGN.md` §3–§5、§9
> - `docs/business-charter.md`、`docs/DEMO.md`、`testing/acceptance/TEST-DATA.md`
> - `docs/PHASE2-DESIGN.md` §2（展示控件与受限富文本）
> - `api/openapi.json`（仅用于确认接口路径、请求/响应字段、状态码）
>
> **覆盖的场景 ID**：SEARCH-01、SEARCH-02、ARCHIVE-01、DASH-01、SEC-01、SEC-02、CONC-01。
>
> **已确认规则**：R-01 运行中组织变更、R-02 编号语义、R-03 CSV 转义、R-04 抄送人附件（详见 §0，直接作为期望结果依据）。
>
> **覆盖的非功能检查**：ENV-01、ENV-02、ENV-03、PERF-01、UAT-01。
>
> **不在本文件范围**：AUTH-01、ORG-01/02、FORM-*、FLOW-*、PERM-*、INIT-*、TASK-*（除并发/越权交叉点）、REJECT-*、RETURN-*、WITHDRAW-*、TERMINATE-*、CC-01、EXT-01、NOTIFY-01；这些由其他验收文件覆盖。

---

## 0. 已确认规则（需求方 2026-11-19 确认，直接作为期望结果依据）

| 规则 | 已确认内容 | 落实用例 |
|---|---|---|
| R-01 运行中组织变更 | 已派发任务保持原处理人不变；流程后续进入新节点时，按进入时**最新组织**解析派单。 | CONC-01-h |
| R-02 编号语义 | **表单编号 = 表单模板编码**（如 `REIMBURSEMENT`）；**实例单号 = 表单内 `auto_number` 字段值**（标识位 + YYYYMMDD + 当日流水）。列表和筛选按此口径区分，两者不得互为别名。 | SEARCH-01-g、ARCHIVE-01-c、CONC-01-g、DASH-01-a/c |
| R-03 CSV 导出转义 | 以 `=`、`+`、`-`、`@` 开头的单元格，导出时在值前加半角单引号 `'`；Excel 显示原文本且不执行公式；**导出说明中注明该规则**。 | SEC-02-d、ARCHIVE-01-c |
| R-04 抄送人附件 | 抄送人附件跟随字段权限：可见字段的附件可下载；hidden 字段及其附件不可见、不可下载。 | SEC-02-f、SEC-01-c |
| D-01 部门主管 | 部门设置的主管人优先，无则沿部门树向上找最近主管，仍无则转平台管理员并标记异常。 | SEARCH-01-h、ARCHIVE-01-b |
| D-02 设计者权限 | 设计者只看自己相关；不可看全量实例/他人审批数据；实例管理与首页管理概览仅管理员。 | DASH-01-c/e、SEC-01-d |
| D-03 并行组退回 | 取消整个并行组及后续令牌，实例保持 RUNNING，在目标节点重派。 | SEC-01-a（引擎回归） |
| D-04 hidden 字段 | 运行中严格隐藏（值、附件元数据、导出/打印都不出现）；终态按归档视角。 | SEC-02-a/b/f、ARCHIVE-01-c、DASH-01-e |
| D-05 归档状态 | 归档列表只含 APPROVED；管理员实例管理可查全部状态。 | ARCHIVE-01-a/b |

---

## 1. 需求歧义与待确认清单

> 这些条目在评审拍板前只作为“待确认”，**不写入用例通过条件**；若某条用例被该歧义阻塞，用例中会显式标注。编号在全文引用。
>
> **编号说明**：原 TBD-01、TBD-02 已由 R-02 关闭；TBD-28 由 R-03 关闭；TBD-05/TBD-15/TBD-17 已由 D-05/D-04/D-02 关闭；TBD-21/TBD-23/TBD-26/TBD-27/TBD-29 按 `P0-DECISIONS.md` §4 默认执行，表中保留为文档回写备忘。TBD 编号不重排。

### 1.1 编号、检索语义与导出

| ID | 类型 | 问题 | 影响 |
|---|---|---|---|
| TBD-03 | 未定义 | **keyword 的匹配范围**：OpenAPI 描述为“标题/编号模糊匹配”；R-02 已定义表单编号与实例单号，但未说明 `keyword` 是否匹配这两个值，还是仅标题。 | SEARCH-01-g、ARCHIVE-01-b |
| TBD-04 | 未定义 | **自动编号生成时机与草稿消费**：TECH 说首次暂存/提交时生成；删除草稿或长期不提交是否消耗当日流水、是否回收号码未定义。 | SEARCH-02-a、CONC-01-g |
| TBD-06 | 未定义 | **CSV 精确列集**：列顺序、子表展开方式、扩展字段列、列名、空值表示、文件名。编号两列的语义已由 R-02 确认（表单编号=模板编码；实例单号=auto_number 值），仍需确认列名/列序。已知约束：展示控件不导出（PHASE2 §2.1）、动态字段有列（TECH M6、DEMO）、UTF-8 BOM（TECH M6）。 | ARCHIVE-01-c |
| TBD-07 | 未定义 | **导出范围与空结果**：导出全部命中行还是当前页；空结果是否输出表头；Content-Type/Content-Disposition 文件名。 | ARCHIVE-01-c、ARCHIVE-01-e |
| TBD-08 | 未定义 | **列表排序与分页稳定性**：SEARCH-FILTER-PLAN 写“保持现有排序”，但 Spec Pack 未定义“现有排序”；分页跨页不重不漏需要排序基线。 | SEARCH-01-e、ARCHIVE-01-a |
| TBD-09 | 未定义 | **区间边界与日期时区**：`between`、`gt/gte/lt/lte` 是否闭区间；date/datetime/time 按表单原值还是上海日界；带时分秒的日期如何比较。 | SEARCH-01-c/d、ENV-03 |
| TBD-10 | 未定义 | **草稿在“我发起的”中的表现**：草稿不索引；应用业务筛选后草稿是否从列表消失；不筛选时草稿是否出现；UI 是否提示“仅已提交单据”。 | SEARCH-01-h |
| TBD-11 | 未定义 | **mine 可见字段按哪个版本判定**：“当前流程发起节点”指当前已发布版本，还是每个实例锁定的流程版本；跨版本权限变化时以谁为准。 | SEARCH-01-h |
| TBD-12 | 未定义 | **配置删除/字段删除后的筛选与元数据**：新版本删除已配置字段后，旧实例是否仍可筛选、元数据是否展示、重建后 `indexed_at` 的语义。 | SEARCH-02-e |
| TBD-13 | 未定义 | **重建期间的在线写入一致性**：重建脚本运行时有新提交/审批，最终索引是否与在线数据一致；是否需要停写窗口或快照。 | SEARCH-02-d/f、ENV-02 |
| TBD-14 | 已知限制待确认 | **长文本 512 字符索引上限**：SEARCH-FILTER-PLAN 风险节写明只索引前缀；产品是否接受 `contains` 对第 513 字符之后不命中；界面是否提示。 | SEARCH-01-b |
| TBD-16 | 未定义 | **筛选值语义与错误侧信道**：选项改名/删除后的历史值、人员/部门 id 是否稳定对外、未知 id 返回空还是 4xx、`has_all` 的 50 值上限；隐藏字段/未知字段/未配置字段是否统一错误码，避免通过 422 差异推断字段存在。 | SEARCH-01-a/d/f、SEC-02-b |

### 1.2 首页

| ID | 类型 | 问题 | 影响 |
|---|---|---|---|
| TBD-18 | 未定义 | **首页指标口径**：今日提交数（创建/提交/重提/按事件）、本周完成数（周起始日、自然周、是否仅 APPROVED）、待办积压数（全局 PENDING 指派还是任务）、运行中（仅 RUNNING 是否含 REJECTED）、本月我发起的已完成（自然月、上海时区、仅 APPROVED）。 | DASH-01-c、ENV-03 |
| TBD-19 | 未定义 | **排序规则**：常用流程“最近发起次数”的时间窗口、并列次序、是否含草稿/驳回重提、是否受发起范围/启用状态过滤；待办/我发起的“最近 5 条”按到达时间还是更新时间。 | DASH-01-a |
| TBD-20 | 未定义 | **单请求/轮询/不闪烁的可判定标准**：是否允许 10 秒轮询同一 overview 接口；“刷新不闪烁”是 DOM 保持还是截图对比；轮询只更新角标与待办预览还是全部区块。 | DASH-01-d |
| TBD-21 | 文档漂移 | **首页接口字段与示例不一致**：PHASE3 §1.3 示例含 `work_stats`，OpenAPI `DashboardOverview` 无该字段；示例 `my_instances.current_node_name` 为字符串，OpenAPI 为 `current_node_names` 数组。首页是否还需要共享表格区块？并行多节点如何展示？ | DASH-01-a/c |

### 1.3 安全

| ID | 类型 | 问题 | 影响 |
|---|---|---|---|
| TBD-22 | 未定义 | **越权返回码统一**：TEST-PLAN 允许 403/404 二选一；需确认是否所有资源统一、是否避免通过状态码差异枚举 ID。 | SEC-01 全部、SEC-02-b |
| TBD-23 | 未定义 | **模板/版本读权限**：普通发起人除 start-options 外能否直接读已发布表单/流程版本；设计者能读全部模板还是仅自己创建/管理的。 | SEC-01-d |
| TBD-24 | 未定义 | **附件策略**：允许的扩展名/MIME、大小上限、图片限制、SVG/HTML 是否允许、文件名清理规则、临时附件绑定与清理、管理员/设计者下载权限。抄送人附件已由 R-04 确认（跟随字段权限），不再待确认。 | SEC-01-c、SEC-02-e |
| TBD-25 | 未定义 | **富文本白名单与处置方式**：允许的 Markdown 子集、链接/图片协议；违规内容在保存/发布时拒绝还是渲染时清洗；预览/详情/打印是否同一清洗。 | SEC-02-c |
| TBD-26 | 未定义 | **单实例导出权限**：发起人/历任处理人/抄送人/管理员/设计者分别能否导出；运行中导出是否包含尚未揭晓字段。 | ARCHIVE-01-d、SEC-02-b |
| TBD-27 | 未定义 | **审计范围与导出内容**：设计者是否完全不可见审计；审计导出是否包含业务字段值/敏感信息；审计是否只追加且无删除 API。 | SEC-01-e |
| TBD-29 | 未定义 | **检索权限矩阵**：非管理员 mine 仅 `start_visible`；管理员 all/related/archive 的具体矩阵；设计者是否可用 mine 筛选自己发起的实例。 | SEARCH-01-h、SEC-02-b |

### 1.4 并发与幂等

| ID | 类型 | 问题 | 影响 |
|---|---|---|---|
| TBD-30 | 未定义 | **幂等响应语义**：重复 `X-Request-Id` 返回 200 既有结果还是 409；同人同任务重复提交、缺省 `expected_version`、过期 version 的返回码。 | CONC-01-a/c |
| TBD-31 | 未定义 | **并发输家语义**：会签同意/驳回、撤回/同意、终止/同意同时发生时，输家请求的返回码、是否写审计/时间线、是否发通知。 | CONC-01-b/c/d/e |
| TBD-32 | 未定义 | **同字段并发“后写覆盖”的时间序**：以服务器提交时间还是动作时间；双方意见/快照是否都保留；不同字段合并的锁粒度。 | CONC-01-f |

### 1.5 环境、性能与 UAT

| ID | 类型 | 问题 | 影响 |
|---|---|---|---|
| TBD-33 | 未定义 | **“上一发布版本”标识**：升级迁移从哪个 tag/commit/数据库快照开始；是否要求可回滚。 | ENV-02 |
| TBD-34 | 未定义 | **Docker 拓扑与配置名**：compose 文件、端口、健康检查、反向代理、卷名、时区环境变量名；PostgreSQL compose 是否随仓库交付；生产默认种子策略（演示账号、示例流程）。 | ENV-01、ENV-03 |
| TBD-35 | 未定义 | **时区展示与周/月边界验证**：`app_timezone` 配置键名与默认值；API 时间是否带偏移（D9 说 naive UTC、前端补 Z）；CSV/导出时间格式；周起始日（周一/周日）；在不等待真实时间下如何构造边界（可注入时钟/预置数据）。 | ENV-03、DASH-01-c |
| TBD-36 | 文档冲突 | **性能验收阈值**：TEST-PLAN §10.3 要求列表/筛选 P95 < 2s；SEARCH-FILTER-PLAN Phase 4 要求 MySQL 单条件 ≤300ms、三条件 ≤500ms。以哪个为验收门槛？SQLite 是否套用？数据集、并发、缓存、采样次数、工具如何统一？ | PERF-01 |
| TBD-37 | 未定义 | **100 节点设计器“可操作”标准**：打开 <3s 之外，选中/保存/发布校验的响应上限；画布与清单是否都测。 | PERF-01 |
| TBD-38 | 未定义 | **UAT 通过标准**：独立完成的判定（允许提问次数、时间上限、可接受绕行）；UAT 环境/账号/数据；签收人。 | UAT-01 |

---

## 2. 用例执行约定与测试基线

- **环境**：每条用例都从 `testing/scripts/e2e-reset.sh` 重置后的独立测试库开始；不依赖其他用例的执行顺序。用例内的表单/流程/实例通过 API 工厂自建，名称前缀 `E2E-<runId>-`。
- **账号**（仅隔离环境，见 `TEST-DATA.md`）：`admin`（平台管理员）、`zhangsan`（技术部普通用户/无关用户反例）、`lisi`（技术部主管）、`wangwu`（财务、财务部主管）、`zhaoliu`（设计者、总公司主管，非管理员）。
- **接口**：前缀 `/api/v1`；认证 `Authorization: Bearer <jwt>`；错误体 `{"detail": {"code", "message", "extra"?}}`。
- **状态码约定**：未认证 401；无权/越权允许 **403 或 404**（以 TBD-22 的统一策略为准），但必须“无数据、无副作用”；参数校验 422；乐观锁/状态冲突 409 `STALE_VERSION`（TECH §3.4）。
- **“无副作用”判定**：实例状态、任务数、待办/已办数、时间线条数、快照数、通知数、审计数均与操作前一致。
- **“可观察”判定**：页面文本/控件状态/URL、HTTP 状态码与 JSON 字段、任务/通知计数、CSV 内容、审计/时间线条目；不以“日志里没报错”代替。
- **`I1`…`I4` 约定**：用例内定义的实例夹具，代表**标题可识别的独立实例**；自动化中用标题或运行前缀映射 ID，不依赖数据库自增顺序。
- **待确认项引用**：TBD 编号见第 1 节；若某条断言被 TBD 阻塞，用例会显式写明“本用例不把该歧义纳入通过条件”。

---

## 3. SEARCH-01：业务字段筛选

### SEARCH-01-a 选项与多选字段：eq / in / has_any / has_all / is_empty

- **需求来源**：TEST-PLAN §6.8 SEARCH-01；SEARCH-FILTER-PLAN“筛选 API”“操作符按 filter_kind”；PHASE3 M13 §3.5；PRD F8.1。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`（归档检索与导出）；`zhangsan`（发起人）；组织树按 TEST-DATA。
  - 表单/流程版本与状态：本用例自建表单 `E2E-S1-选项`，含单选 `leaveType`（选项：年假/事假/病假）与多选 `modules`（选项：A/B/C），二者均发起阶段可见；流程为单审批节点，发布后由 `zhangsan` 发起并审批至 APPROVED。
  - 实例状态与数据（均 APPROVED）：
    - I1：`leaveType=年假`，`modules=[A,B]`。
    - I2：`leaveType=事假`，`modules=[B]`。
    - I3：`leaveType=病假`，`modules=[C]`。
    - I4：`leaveType=年假`，`modules=[]`（空多选）。
- **步骤**：
  1. 设计者通过 `PUT /form-templates/{id}/search-fields` 将 `leaveType`、`modules` 勾选为可检索；`admin` 调用 `GET /instances/search-fields?flow_template_id=<id>&scope=archive`，确认字段、`filter_kind`（option/multi_option）与选项并集。
  2. 调用 `GET /instances/archive?flow_template_id=<id>&filters=[{"field":"leaveType","op":"eq","value":"年假"}]`。
  3. 调用 `...&filters=[{"field":"leaveType","op":"in","value":["年假","病假"]}]`。
  4. 调用 `...&filters=[{"field":"modules","op":"has_any","value":["A"]}]`，再调用 `has_any ["A","C"]`。
  5. 调用 `...&filters=[{"field":"modules","op":"has_all","value":["A","B"]}]`。
  6. 调用 `...&filters=[{"field":"modules","op":"is_empty","value":null}]`。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 2 返回 I1、I4；步骤 3 返回 I1、I3、I4；步骤 4 第一次仅 I1，第二次 I1、I3；步骤 5 仅 I1；步骤 6 仅 I4。每步 `total` 与命中条数一致。
  2. 数据副作用：无写入；实例状态、任务、快照、索引均不变。
  3. 通知/审计副作用：无新增通知；检索读操作不产生业务动作审计（若系统记录访问日志，不作为业务审计计）。
- **反例/边界**：
  - `eq` 一个不在选项并集内的值（如“婚假”）返回 0 条而不是 500。
  - 对空多选 `has_any` 返回 0 条；`is_empty` 只命中 I4。
  - 选项按 `filter_kind` 只接受 `eq/in`；对 option 使用 `contains` 见 SEARCH-01-f。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：选项改名/删除后的历史值语义（TBD-16）。

### SEARCH-01-b 文本字段：contains / eq / is_empty / is_not_empty（含大小写与通配符转义）

- **需求来源**：TEST-PLAN §6.8 SEARCH-01；SEARCH-FILTER-PLAN“操作符”“文本统一 casefold”“contains 使用 autoescape”；PHASE3 M13。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起。
  - 表单/流程：自建表单 `E2E-S1-文本`，含单行 `subject`、多行 `remark`，均发起可见且配置为可检索（text）；实例审批至 APPROVED。
  - 实例数据：
    - I1：`subject="Alpha 报销"`，`remark="有票据"`。
    - I2：`subject="alpha 差旅"`，`remark=""`。
    - I3：`subject="Beta"`，`remark=null`。
    - I4：`subject="alphabet"`，`remark="100%_done"`。
- **步骤**：
  1. `filters`：`subject contains "ALPHA"`。
  2. `subject eq "alpha 差旅"`。
  3. `remark is_empty`；再 `remark is_not_empty`。
  4. `remark contains "%_"`（验证 `%`、`_` 不被当作 SQL 通配符）。
  5. 在归档页 E2E 中输入相同条件，确认列表与 API 一致。
- **期望结果**：
  1. 步骤 1 命中 I1、I2、I4（casefold 后包含）；步骤 2 仅 I2；步骤 3 `is_empty` 命中 I2、I3，`is_not_empty` 命中 I1、I4；步骤 4 仅 I4。
  2. 结果 `total` 与 E2E 列表条数一致；页面无 500、无空白列表。
  3. 数据副作用：无写入；索引不重建。
- **反例/边界**：
  - 文本超过 512 字符时，仅前缀索引（TBD-14）；本用例不把“第 513 字符后是否命中”纳入通过条件。
  - 关键字含 `%`、`_`、`\` 时必须按字面匹配，不得扩大结果集。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-14。

### SEARCH-01-c 数字与公式字段：eq / 比较 / between / 数值规范化

- **需求来源**：TEST-PLAN §6.8 SEARCH-01；SEARCH-FILTER-PLAN“操作符按 filter_kind”“公式 arithmetic/subtable_sum 视为 number”“数值 Decimal”；PHASE3 M13。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起。
  - 表单/流程：自建表单 `E2E-S1-数字`，含数字 `amount`、子表 `items` 与公式 `total=子表合计`；`amount`、`total` 配置为可检索（number）；实例审批至 APPROVED。
  - 实例数据：I1 `amount=100.5,total=500`；I2 `amount=2000,total=2500`；I3 `amount=3000,total=4000`；I4 `amount=250,total=1000`。
- **步骤**：
  1. `amount eq 2000`；`amount eq 100.50`。
  2. `amount gt 2000`；`gt 250`；`gte 2000`；`lt 3000`；`lte 2000`。
  3. `amount between [101, 2999]`；`total between [1000, 2600]`。
  4. `total gt 2000`；`total eq 500`。
  5. 非法：`between` 只传一个值；`between ["abc", 2000]`；`gt "x"`。
- **期望结果**：
  1. `eq 2000` → I2；`eq 100.50` → I1（100.5 与 100.50 数值相等）。
  2. `gt 2000` → I3；`gt 250` → I1、I2、I3；`gte 2000` → I2、I3；`lt 3000` → I1、I2、I4；`lte 2000` → I1、I2、I4。
  3. `amount between [101,2999]` → I2、I4；`total between [1000,2600]` → I1、I2、I4（两端语义见 TBD-09，本用例只使用明确位于区间内/外的值）。
  4. `total gt 2000` → I2、I3；`total eq 500` → I1。
  5. 非法请求均 422，`detail.code` 存在，页面/接口无 500，无数据返回。
  6. 数据副作用：无写入；索引不变。
- **反例/边界**：
  - 浮点精度：`100.500000` 与 `100.5` 必须视为相等；不得因字符串比较漏命中。
  - `between` 两端恰好等于边界值的实例：按 TBD-09 评审结论执行；评审前不纳入通过条件。
- **自动化位置**：`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-09、TBD-16。

### SEARCH-01-d 日期/时间/布尔/人员/部门/多选人员部门

- **需求来源**：TEST-PLAN §6.8 SEARCH-01；SEARCH-FILTER-PLAN“操作符按 filter_kind”“日期/时间按表单字符串写入”“人员/部门正整数”；PHASE3 M13。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；用户 `lisi`、`wangwu` 启用；部门技术部、财务部存在。
  - 表单/流程：自建表单含 `leaveDate`（date）、`submitAt`（datetime）、`startTime`（time）、`urgent`（switch）、`owner`（人员单选）、`reviewers`（人员多选）、`dept`（部门单选）、`depts`（部门多选）；全部配置为可检索；实例审批至 APPROVED。
  - 实例数据：
    - I1：`leaveDate=2026-11-19`，`submitAt=2026-11-19T09:30:00`，`startTime=09:30`，`urgent=true`，`owner=lisi`，`reviewers=[lisi,wangwu]`，`dept=技术部`，`depts=[技术部,财务部]`。
    - I2：`leaveDate=2026-11-20`，`submitAt=2026-11-20T18:00:00`，`startTime=18:00`，`urgent=false`，`owner=lisi`，`reviewers=[lisi]`，`dept=技术部`，`depts=[技术部]`。
    - I3：`leaveDate=2026-12-01`，`submitAt=2026-12-01T08:00:00`，`startTime=08:00`，`urgent=true`，`owner=wangwu`，`reviewers=[]`，`dept=财务部`，`depts=[财务部]`。
    - I4：`leaveDate=2026-10-31`，`submitAt=2026-10-31T23:59:00`，`startTime=23:59`，`urgent=false`，`owner=wangwu`，`reviewers=[wangwu]`，`dept=财务部`，`depts=[]`。
- **步骤**：
  1. `leaveDate eq 2026-11-19`；`leaveDate between [2026-11-01, 2026-11-30]`。
  2. `submitAt between [2026-11-19T00:00:00, 2026-11-20T23:59:59]`。
  3. `startTime between ["08:00","10:00"]`。
  4. `urgent eq true`；`owner eq <lisi user id>`；`owner in [<lisi>,<wangwu>]`。
  5. `reviewers has_any [<wangwu>]`；`reviewers has_all [<lisi>,<wangwu>]`。
  6. `dept eq <技术部 id>`；`dept in [<技术部>,<财务部>]`；`depts has_any [<财务部>]`。
- **期望结果**：
  1. `leaveDate eq` → I1；`between`（仅取明确区间内值）→ I1、I2。
  2. datetime between → I1、I2。
  3. time between → I1（09:30）；I3（08:00）为边界值，按 TBD-09 决定是否纳入。
  4. `urgent eq true` → I1、I3；`owner eq lisi` → I1、I2；`owner in` → I1、I2、I3、I4。
  5. `reviewers has_any[wangu]` → I1、I4；`has_all[lisi,wangwu]` → I1。
  6. `dept eq` → I1、I2；`dept in` → I1、I2、I3、I4；`depts has_any[财务部]` → I1、I3。
  7. 日期值在页面详情/导出中仍为 `2026-11-19`，不发生时区位移（ENV-03 交叉验证）。
  8. 数据副作用：无写入。
- **反例/边界**：
  - `urgent` 使用 `contains`/`between` → 422。
  - 人员/部门传 0、负数、字符串 id → 422；不存在的正整数 id 行为见 TBD-16（本用例只用存在的 id）。
  - `reviewers has_all` 空数组 → 422（值不合法）；具体错误码见 TBD-16。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-09、TBD-16。

### SEARCH-01-e 多条件 AND、分页、URL 状态与清空

- **需求来源**：SEARCH-FILTER-PLAN“所有条件 AND”“最多 10 个条件”“前端筛选 UI：page=1、route.query、切换 tab/流程清空”；PHASE3 §3.4；TEST-PLAN SEARCH-01。
- **优先级**：P0
- **验证层**：浏览器 E2E + API
- **前置条件**：
  - 角色与组织：`admin` 归档；`zhangsan` 用于 mine 的 URL 状态。
  - 表单/流程：自建表单含 `leaveType`（选项）、`amount`（number）、`leaveDate`（date）；配置可检索；已审批实例 6 条（I1–I6），条件组合见步骤。
  - 实例数据：至少 3 条同时满足“年假 + amount>1000 + 2026-11”，另外 3 条分别只满足其中 1–2 个条件。
- **步骤**：
  1. 归档页设置三个条件（AND），记录结果集合 R。
  2. 设置 `page=1&size=2`，逐页抓取直到最后一页，合并 ID。
  3. 修改任一条件，确认页码回到 1；清空条件，确认回到未筛选状态。
  4. 刷新页面、复制 URL 到新标签页，确认条件与结果恢复。
  5. 在“我发起的”mine tab 重复设置条件、刷新恢复；再切换到“待办”tab 或切换流程，确认筛选被清空。
  6. 连续添加 10 个条件（可重复同一字段不同操作符，只要合法）；确认第 11 个无法添加（UI）。
- **期望结果**：
  1. 结果集合 R 恰为同时满足三个条件的实例；API `total` 等于 R 的大小。
  2. 分页合并后的 ID 集合 = R，无重复、无遗漏；每页 `size` 不超过 2。
  3. 修改条件后 `page` 重置为 1；清空后返回未筛选列表，URL 中不再保留旧条件。
  4. 刷新后条件、页码、结果一致；URL 中的 `filters` 可解析且与界面一致。
  5. 切换到待办/切换流程后，mine 的筛选条件被清空，列表回到该 tab 的默认结果。
  6. 第 10 个条件可提交；第 11 个在 UI 不可添加；直接调 API 见 SEARCH-01-f（422）。
  7. 数据副作用：无写入；检索不生成通知/审计动作。
- **反例/边界**：
  - URL 中手工填入非法 `filters`（截断 JSON）时，页面给出可理解的错误/回退，不白屏、不发 500（错误呈现方式见 TBD-08；本用例只断言“不白屏、不到空数据假装 0 条”）。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`
- **需求待确认项**：TBD-08、TBD-16。

### SEARCH-01-f 非法筛选：422、错误码、无 500、无副作用

- **需求来源**：SEARCH-FILTER-PLAN“解析失败 422 FILTER_INVALID；字段不在白名单 422；操作符/值不合法 422；flow_template_id 必填 422 FLOW_TEMPLATE_REQUIRED；filters 最长 8192 字节、最多 10 个条件”“非管理员 related/all 拒绝 FILTER_SCOPE_NOT_SUPPORTED”；TECH §5 错误体；OpenAPI 422。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan`（普通用户）。
  - 表单/流程：自建表单，配置至少 1 个可检索字段；存在可访问实例；已发布流程。
  - 数据库：SQLite（e2e 库）；MySQL/PG 的同一矩阵在 ENV-02 复核。
- **步骤**（逐条独立发请求，互不依赖）：
  1. 带 `filters` 但不带 `flow_template_id`。
  2. `filters` 不是合法 JSON（如 `[{"field":`）。
  3. 字段不在该模板可检索白名单（如 `undefined_field`）。
  4. 对 number 字段使用 `contains`；对 option 字段使用 `between`。
  5. `between` 只传一个值；值类型错误（number 传 `"abc"`）；日期传 `2026-13-40`。
  6. 条件数 11 个。
  7. `filters` 序列化后超过 8192 字节。
  8. 非管理员 `zhangsan` 使用 `scope=related` 或 `scope=all` 带 `filters`。
  9. `has_all` 传 51 个值。
- **期望结果**：
  1. 步骤 1 → 422，`detail.code=FLOW_TEMPLATE_REQUIRED`。
  2. 步骤 2/4/5/6/7/9 → 422；步骤 2 的 `detail.code` 为 `FILTER_INVALID`（文档明确）；其余 `detail.code` 非空，错误信息可读。
  3. 步骤 3 → 422；错误体不得回显该字段的任何实例值/选项值。
  4. 步骤 8 → 422，`detail.code=FILTER_SCOPE_NOT_SUPPORTED`；不返回任何实例。
  5. 所有请求均无 500、无内部堆栈、无部分结果；错误响应不包含 SQL/表名/异常类型。
  6. 数据副作用：实例、任务、索引、通知、审计均无变化。
- **反例/边界**：
  - 空 `filters=[]`：按“无筛选”处理还是 422，文档未定义；见 TBD-07/TBD-16，本用例不纳入通过条件。
  - 非法字段与合法但无结果的字段：不得通过“422 vs 0 条”推断隐藏字段是否存在（TBD-16）。
- **自动化位置**：`backend/tests/test_acceptance_search.py`；`testing/e2e/specs/search-export.spec.ts`
- **需求待确认项**：TBD-07、TBD-16、TBD-29。

### SEARCH-01-g 表单编号与实例单号：模板编码 vs auto_number 值，两列两个口径

- **需求来源**：TEST-PLAN §6.8“表单编号与实例单号不混用”；需求方 2026-11-19 确认 R-02；TECH §3.3“自动编号（标识位 + YYYYMMDD + 当日流水）”；REQ-OPT-FLOW-CONFIG §2/§5“编号 `REQ202611110004`”；PRD F8.1；DEMO 步骤 9。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起。
  - 表单/流程：自建表单模板，**表单编号（模板编码）= `E2E-S1-NO`**；表单含顶层单行文本字段 `reqNo` 配置为 `auto_number`（标识位 `REQ`、4 位流水），即**实例单号**；`reqNo` 配置为可检索（text）；流程单审批节点，发布。
  - 实例数据：I1、I2 均审批至 APPROVED，`reqNo` 分别为 `REQ<YYYYMMDD>0001`、`REQ<YYYYMMDD>0002`；两条实例属于同一表单模板，因此表单编号相同、实例单号不同。
- **步骤**：
  1. 在归档列表/详情/导出中分别读取 I1、I2 的“表单编号”和“实例单号”两列。
  2. `GET /instances/archive?flow_template_id=<id>&filters=[{"field":"reqNo","op":"eq","value":"<I1 的实例单号>"}]`。
  3. 用模板编码作为业务字段值筛选：`filters=[{"field":"reqNo","op":"eq","value":"E2E-S1-NO"}]`；再用 `flow_template_id=<id>` 列出该表单全部实例。
  4. `keyword=<I1 的实例单号>`：记录结果，但本用例不把它作为通过条件（TBD-03）。
  5. E2E 归档列表/详情/CSV：确认“表单编号”和“实例单号”是两个不同标签、两个不同值，不互为别名，也不发生列错位。
- **期望结果**：
  1. I1、I2 的表单编号均为 `E2E-S1-NO`；实例单号分别为 `REQ<YYYYMMDD>0001`、`REQ<YYYYMMDD>0002`，互不相同，且都不等于模板编码。
  2. 步骤 2 只返回 I1，`total=1`；不得因为 I2 的实例单号包含相同日期段而误命中，也不得因为两者表单编号相同而把 I2 一并返回。
  3. 步骤 3 用模板编码按 `reqNo` 过滤 → 0 条；用 `flow_template_id` → I1、I2 都返回，且页面“表单编号”仍显示 `E2E-S1-NO`。
  4. 步骤 5 导出 CSV 中存在“表单编号”和“实例单号”两个不同列：表单编号列值为 `E2E-S1-NO`，实例单号列值为 `reqNo` 值；`auto_number` 若另作为动态字段列出现，其值必须等于实例单号，不得显示成模板编码。
  5. 数据副作用：无写入；实例单号在再次查看时保持不变（本用例不触发重提）。
- **反例/边界**：
  - 同一表单下两条实例表单编号相同是正常的；实例单号重复才是错误。
  - 用 I2 的实例单号作为 `reqNo eq` 值 → 只命中 I2，不得同时命中 I1 返回两条。
  - 以模板编码作为实例单号筛选 → 0 条，不得把“表单编号”当作“实例单号”匹配。
  - `keyword` 是否匹配表单编号/实例单号仍未定义（TBD-03），步骤 4 只记录，不作为失败依据。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-03、TBD-04、TBD-06。

### SEARCH-01-h “我发起的”筛选权限：隐藏字段、草稿、scope 拒绝

- **需求来源**：SEARCH-FILTER-PLAN“scope=mine：非管理员只返回 start_visible=True，且按当前流程发起节点 resolve_field_permissions 判定可见的字段；防止通过筛选推断隐藏补充字段”“非管理员 related/all + filters 拒绝 FILTER_SCOPE_NOT_SUPPORTED”“草稿不索引”；PHASE3 §3.5；TEST-PLAN SEARCH-01。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（普通发起人，非管理员）；`lisi`（审批人）；`admin`。
  - 表单/流程：自建表单含 `leaveType`（发起可见，配置可检索）与 `actualAmount`（`visible_at_start=false`，仅财务填写节点可编辑，也配置为可检索）；流程：部门经理审批 → 财务填写节点；发布。
  - 实例状态与数据：`zhangsan` 保存草稿 D（`leaveType=年假`，未提交）；提交实例 S（`leaveType=事假`），当前在部门经理节点；`actualAmount` 尚未填写。
- **步骤**：
  1. `zhangsan` 调 `GET /instances/search-fields?flow_template_id=<id>&scope=mine`。
  2. `zhangsan` 调 `GET /instances?scope=mine&flow_template_id=<id>&filters=[{"field":"actualAmount","op":"is_empty"}]`。
  3. `zhangsan` 调 `GET /instances?scope=mine&flow_template_id=<id>&filters=[{"field":"leaveType","op":"eq","value":"事假"}]`。
  4. `zhangsan` 调 `GET /instances?scope=related&flow_template_id=<id>&filters=[...]`；再 `scope=all`。
  5. `zhangsan` 调 `GET /instances/search-fields?...&scope=archive`。
  6. E2E 打开“我发起的”，应用业务筛选，观察草稿 D 是否出现及页面提示。
- **期望结果**：
  1. 步骤 1 返回 `leaveType`；**不返回** `actualAmount`（或明确标记为不可筛选），且响应中不含 `actualAmount` 的值。
  2. 步骤 2 → 422；错误体不包含 `actualAmount` 的选项/值，不因“is_empty 可执行”泄露字段存在性。
  3. 步骤 3 返回 S；草稿 D **不出现**（草稿无索引，见 TBD-10 对未筛选列表的约定）。页面有“仅已提交单据可筛选”或等价提示。
  4. 步骤 4 → 422，`detail.code=FILTER_SCOPE_NOT_SUPPORTED`；无实例数据。
  5. 步骤 5 → 403/404（归档筛选仅管理员，TBD-29）；不返回字段列表。
  6. 数据副作用：无写入；草稿仍是草稿，S 状态不变。
- **反例/边界**：
  - 在请求中伪造 `scope=mine` 但传入管理员才可见的字段 → 422。
  - 切换流程后筛选清空（E2E，与 SEARCH-01-e 重复但独立执行）。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-10、TBD-11、TBD-29（默认）。

---

## 4. SEARCH-02：索引同步与重建

### SEARCH-02-a 提交/草稿的索引同步：草稿不可检索，提交后立即可查

- **需求来源**：SEARCH-FILTER-PLAN“同步点：_start_round（提交/重提）与 act 同一事务内重建；草稿不索引”“空值写 empty 行；多选一值一行”；PHASE3 M13 §3.3 Phase 0/3.5；TEST-PLAN SEARCH-02。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起。
  - 表单/流程：自建表单含 `leaveType`（option）、`tags`（multi_option）、`note`（text），均配置可检索；流程单审批节点，发布。
  - 实例数据：本用例内新建；初始无实例。
- **步骤**：
  1. `zhangsan` 创建草稿 D（`leaveType=年假`，`tags=[A,B]`，`note=""`），不提交。
  2. `admin` 以 `GET /instances?scope=all&flow_template_id=<id>&filters=[leaveType eq 年假]` 查询。
  3. `zhangsan` 提交 D → 实例 S；记录 `started_at`。
  4. 立即（下一次请求）用同一筛选查询；再用 `tags has_any [B]`、`tags has_all [A,B]`、`note is_empty` 查询。
  5. 另建草稿 D2 并删除；确认不产生可检索实例。
- **期望结果**：
  1. 步骤 2 返回 0 条（草稿未索引），不报 500。
  2. 步骤 4 第一次查询立即返回 S（同一事务同步，无“等一会儿才出现”）；`tags` 两个操作符均命中 S；`note is_empty` 命中 S。
  3. 多选值 `[A,B]` 不导致 S 在结果中出现两次（`total=1`）。
  4. 步骤 5 删除草稿后仍 0 条；不产生孤儿索引（以筛选结果判断）。
  5. 数据副作用：只有 S 被索引；D/D2 无索引；S 的状态为 RUNNING。
- **反例/边界**：
  - 提交请求失败（如必填缺失）时不得留下索引行，见 SEARCH-02-c。
  - 空字符串/`null`/`[]` 都按 `empty` 行处理；`is_empty` 命中，`is_not_empty` 不命中。
- **自动化位置**：`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-04、TBD-13。

### SEARCH-02-b 审批修改后的索引更新：当前值可查，历史快照不可查

- **需求来源**：SEARCH-FILTER-PLAN“act（同意/驳回/退回/填写）同一事务内重建”“索引是当前数据派生读模型”；PRD §3.4 字段累积；TEST-PLAN SEARCH-02“新增/修改实例后可检索”。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起；`lisi` 审批；`wangwu` 财务填写。
  - 表单/流程：自建表单含 `actualAmount`（number，仅财务填写节点可编辑）、`leaveType`（发起可见）；二者配置可检索；流程：部门经理审批 → 财务填写 → 结束；发布。
  - 实例状态：`zhangsan` 提交，当前在部门经理节点；`actualAmount` 为空。
- **步骤**：
  1. `lisi` 同意部门经理（`actualAmount` 仍为空）。
  2. `admin` 查询 `actualAmount is_empty` → 命中；`actualAmount eq 500` → 0。
  3. `wangwu` 在财务节点填写 `actualAmount=500` 并提交（填写节点动作 SUBMIT）。
  4. 立即查询 `actualAmount eq 500` → 命中；`is_empty` → 不命中；`eq 400` → 0。
  5. 若流程还有下一审批节点，让其驳回；查询 `eq 500`。
  6. 发起人重提并改为 `800`；查询 `eq 800` 与 `eq 500`。
  7. 通过时间线读取修改前快照（F4.6），确认快照仍为旧值；用 `eq 500` 搜索不得命中当前索引（历史快照不参与搜索）。
- **期望结果**：
  1. 步骤 2：`is_empty` 命中该实例；`eq 500` 0 条。
  2. 步骤 4：`eq 500` 恰命中 1 条（`total=1`，不分页重复）；`is_empty`/`eq 400` 0 条。
  3. 步骤 5：驳回不改变 `current_data`，`eq 500` 仍命中 1 条。
  4. 步骤 6：`eq 800` 命中 1 条；`eq 500` 0 条（索引替换而不是追加）。
  5. 步骤 7：时间线/快照仍可看到 500，但搜索结果不因快照保留而返回该实例的旧值。
  6. 数据副作用：每次动作后索引为该实例当前值；无重复行；实例状态按动作变化。
- **反例/边界**：
  - 同一次动作同时修改两个可检索字段：两个字段的索引都更新（不出现只更新一个）。
  - 动作失败（如必填校验不过）时索引不更新，见 SEARCH-02-c。
- **自动化位置**：`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-09、TBD-13。

### SEARCH-02-c 索引与业务写入的原子性：失败动作不留下半套索引

- **需求来源**：SEARCH-FILTER-PLAN“与引擎同一事务内重建索引”“先 DELETE 再批量 INSERT；flush 不 commit”；TECH §4.3 事务骨架；TEST-PLAN SEARCH-02。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起；`lisi` 审批。
  - 表单/流程：自建表单含必填 `title`、数字 `amount`（配置可检索）；流程单审批节点；发布。
  - 实例状态：一条已提交实例 S（`amount=100`）在审批节点；一条草稿 D。
- **步骤**：
  1. 提交 D 时故意缺失必填 `title`，期望 422。
  2. 查询 D 是否可被 `amount eq <D 值>` 检索，且 D 仍为草稿。
  3. 对 S 的审批任务提交非法 `field_patch`（如 `amount` 传超范围/非法类型，按表单值规则应被服务端拦截），期望 4xx。
  4. 查询 `amount eq 100` 与 `amount eq <非法值>`。
  5. 同一任务用合法 patch 重试并成功；查询新旧值。
- **期望结果**：
  1. 步骤 1 → 422，D 仍为 DRAFT；步骤 2 查询 0 条。
  2. 步骤 3 → 4xx，实例 `current_data` 仍为 100，任务仍 PENDING，时间线/快照数不变。
  3. 步骤 4：`eq 100` 恰命中 1 条；非法值 0 条；不出现同一实例的两套索引行（total 不为 2）。
  4. 步骤 5：成功后 `eq 新值` 命中 1 条，`eq 100` 0 条；只有一次动作/快照。
  5. 数据副作用：失败动作无实例/索引/通知/审计写入；成功动作只写一次。
- **反例/边界**：
  - 索引构建过程中抛错（可通过非法字段配置/类型冲突场景在测试 fixture 中模拟）：事务回滚后实例动作也不得部分落库；本用例至少验证“动作失败 → 索引不变”，构建期异常由 SEARCH-02-f/ENV-02 补充。
- **自动化位置**：`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-13。

### SEARCH-02-d 重建脚本与页面重建：dry-run、幂等、范围、计数

- **需求来源**：SEARCH-FILTER-PLAN“重建命令：--all / --flow-template-id / --form-template-id / --batch-size 500 / --dry-run；分批 commit，幂等；完成后更新 indexed_at”“页面‘重建索引’按钮（先保存配置，再重建该表单下全部已提交实例）”；PHASE3 §3.5；TEST-PLAN SEARCH-02。
- **优先级**：P0
- **验证层**：API + 命令行（测试环境）
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起。
  - 表单/流程：自建表单 `E2E-S2-重建`，含 `leaveType`（option）与 `amount`（number）；先不配置可检索；已有 5 条已提交实例（其中 3 条 APPROVED、2 条 RUNNING），1 条草稿。
  - 环境：独立测试库；不与其他用例共享数据。
- **步骤**：
  1. 设计者把 `leaveType`、`amount` 配置为可检索，记录 `SearchFieldSaveResult` 与 `indexed_at`。
  2. 查询 `leaveType` 过滤 → 期望存量实例暂不可查；记录基线。
  3. 运行 `python -m app.scripts.rebuild_search_index --form-template-id <id> --dry-run`。
  4. 再次查询 → 结果与步骤 2 相同；`indexed_at` 不变。
  5. 运行 `--form-template-id <id>`（记录输出的 total/processed）；再查询。
  6. 重复运行同一命令；再运行 `--batch-size 1`；再运行 `--flow-template-id <id>`；最后 `--all`。
  7. 调用页面/接口 `POST /form-templates/{id}/search-fields/rebuild`，记录 `SearchRebuildResult`。
- **期望结果**：
  1. 步骤 1 返回 `added=2`、`needs_backfill=true`；`indexed_at` 为空或表明未回填。
  2. 步骤 2 存量实例过滤结果为 0（新配置尚未回填），但新提交实例可查（若本用例另建一条）。
  3. 步骤 3/4 dry-run 不改变任何结果、不写索引、不改 `indexed_at`。
  4. 步骤 5 后存量已提交实例可被过滤命中；`total` 等于该表单已提交实例数（5），不含草稿；`processed` 等于 `total`（允许分页批次累加）。
  5. 步骤 6 重复执行结果一致（幂等）：相同过滤结果、相同 total、无重复行（`total` 不翻倍）；`--batch-size 1` 不改变结果；范围参数只影响目标表单/流程。
  6. 步骤 7 返回 `total/processed`，与 CLI 对同一表单的结果一致；页面提示可读；重建后过滤结果与在线数据一致。
  7. `indexed_at` 在成功回填后非空；后续新提交无需重建即可查。
  8. 数据副作用：仅索引派生数据变化；实例/任务/快照/通知/审计不变（重建不应写业务审计，除非文档另有规定）。
- **反例/边界**：
  - 重建时有新提交/审批并发（TBD-13）：本用例可在脚本运行同时提交一条实例，要求最终过滤结果包含它且不重复；若评审决定需要停写窗口，则改为在窗口内执行。
  - `--dry-run` 输出格式未定义（TBD-13）；本用例只要求“可观察地不写入 + 输出计数”。
- **自动化位置**：`backend/tests/test_acceptance_search.py`（CLI 用 subprocess 调用）；`testing/e2e/specs/search-export.spec.ts`（页面按钮）
- **需求待确认项**：TBD-12、TBD-13、TBD-36。

### SEARCH-02-e 配置生命周期：新增/删除/重新新增、字段从新版本删除、复制模板

- **需求来源**：SEARCH-FILTER-PLAN“配置删除：同事务删除该模板所有实例对应行；配置新增：新提交立即有索引，存量由重建回填”“新版本删除已配置字段：允许发布，但新实例不会索引该字段”“复制模板带配置”；PHASE3 §3.5。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin` 或 `zhaoliu`（设计者）；`zhangsan` 发起。
  - 表单/流程：自建表单 v1 含 `leaveType`、`amount`、`note`；已配置 `leaveType`、`amount` 可检索；已有 2 条已提交实例（已重建/已索引）；已发布流程锁定 v1。
- **步骤**：
  1. 追加 `note` 为可检索字段：`PUT search-fields`，记录 `added/removed/needs_backfill`。
  2. 查询 `note` 过滤存量实例 → 预期暂不可查；运行重建后 → 可查。
  3. 移除 `amount`：再次 `PUT`，只保留 `leaveType`、`note`。
  4. 查询 `amount` 过滤 → 422（已不在白名单）；查询元数据 → 不再出现 `amount`；再新增回来 → `needs_backfill=true`，重建后可查。
  5. 发布表单 v2：删除 `note` 字段；发布校验应允许；新发起一条实例（走新流程版本或重新发布流程锁 v2）。
  6. 用 `note` 过滤 → 旧实例仍可查（历史版本），新实例不命中（该版本无此字段）。
  7. 复制该表单模板：复制后的模板应带上可检索配置（字段在复制版本中存在时）。
- **期望结果**：
  1. 步骤 1 `added=1`、`needs_backfill=true`；步骤 2 重建前 0 条，重建后命中旧实例。
  2. 步骤 3 `removed=1`；步骤 4 过滤请求 422，元数据不含 `amount`；重新新增后需重建，重建后旧实例可查。
  3. 步骤 5 发布成功（文档允许删除已配置字段）；步骤 6 旧实例可查、新实例不可查；元数据对“当前版本不存在字段”的处理按 TBD-12 执行（本用例只断言过滤结果）。
  4. 步骤 7 复制模板的 `search-fields` 配置与源模板一致（新增字段仍在，除非源字段在复制版本中不存在）。
  5. 数据副作用：删除配置后对应索引行被清理（以“重新新增后必须回填”可观察）；实例数据不变。
- **反例/边界**：
  - 删除配置后立即查询旧字段 → 422，不得“字段不在白名单却返回 200 空结果”造成可推断差异（TBD-16）。
  - 发布新版本时字段类型变化 → 见 SEARCH-02-f。
- **自动化位置**：`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-12、TBD-16。

### SEARCH-02-f 可检索字段配置约束：上限、排除类型、选项、跨版本类型冲突

- **需求来源**：SEARCH-FILTER-PLAN“每个模板最多 20 个可检索字段；单选/多选/级联必须有选项；同一 key 跨版本 filter_kind 必须一致，否则发布阻断 SEARCH_FIELD_TYPE_CONFLICT；排除子表列/attachment/image/subtable/display”；PHASE3 §3.5；PHASE2 §2.1（展示控件不进入数据）。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhaoliu`（设计者，非管理员）；`admin`。
  - 表单/流程：自建模板，含顶层文本、数字、单选（有选项）、多选、级联（有选项）、子表（含列）、附件、图片、展示控件（heading/rich_text），以及公式字段；无已发布流程依赖。
- **步骤**：
  1. `PUT search-fields` 选中 21 个字段（可重复构造合法 key 的 21 个顶层字段）。
  2. 尝试选中子表、子表列、附件、图片、展示控件。
  3. 选中一个未配置选项的单选/多选/级联字段。
  4. 发布 v1：`leaveType` 为单选（option）；发布 v2 将同一 key 改为多行文本（text），尝试发布。
  5. 复制模板/导入导出后检查配置（若文档覆盖）。
- **期望结果**：
  1. 步骤 1 → 422（最多 20 个）；错误信息指出上限。
  2. 步骤 2 → 422 或字段列表不提供选择；不得静默接受这些类型。
  3. 步骤 3 → 422，提示需配置选项。
  4. 步骤 4 的 v2 发布被阻断，`detail.code=SEARCH_FIELD_TYPE_CONFLICT`；v1 仍可用，已有实例/索引不受影响。
  5. 步骤 5 若复制模板，配置随模板复制；导入导出不得产生非法配置（以校验结果判断）。
  6. 数据副作用：失败保存/发布不改变现有配置与索引；成功保存写审计 `UPDATE / FORM_TEMPLATE`（SEARCH-FILTER-PLAN）。
- **反例/边界**：
  - 同一 key 跨版本类型一致但选项变化（并集）→ 允许，历史值仍按索引行匹配；具体历史选项语义见 TBD-16。
  - 非设计者调用 `PUT search-fields` → 403，见 SEC-01-d。
- **自动化位置**：`backend/tests/test_acceptance_search.py`；`testing/e2e/specs/search-export.spec.ts`（设计器入口）
- **需求待确认项**：TBD-12、TBD-16、TBD-23。

---

## 5. ARCHIVE-01：归档列表与导出

### ARCHIVE-01-a 归档默认只含已通过实例；分页可遍历

- **需求来源**：TEST-PLAN §6.8 ARCHIVE-01“只含已通过实例”；PRD F8.1；OpenAPI `/instances/archive`（默认 APPROVED）；DEMO 步骤 9。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起；`lisi` 审批；`wangwu` 财务。
  - 表单/流程：自建表单与单审批流程，发布；本用例创建 6 条实例：
    - A1–A3：APPROVED（其中 A3 有扩展字段/动态字段，若流程支持）。
    - R1：RUNNING（停在审批节点）。
    - J1：REJECTED（驳回后未重提）。
    - W1：WITHDRAWN（提交后无人处理时撤回）。
    - T1：TERMINATED（管理员终止）。
  - 所有实例标题带 `E2E-<runId>-` 前缀，便于断言。
- **步骤**：
  1. `admin` 调 `GET /instances/archive`（不传 status）。
  2. 传 `status=APPROVED`。
  3. 以 `size=2` 分页抓取全部页。
  4. E2E 打开“审批管理 → 实例管理/归档”，观察默认列表。
- **期望结果**：
  1. 步骤 1 只返回 A1–A3，`total=3`；R1/J1/W1/T1 均不出现。
  2. 步骤 2 与步骤 1 结果相同。
  3. 分页合并后仍为 A1–A3，无重复、无遗漏；每页不超过 2 条。
  4. 页面列表状态列显示“已通过”，不混入其他状态；空数据区域不报错。
  5. 数据副作用：无写入；实例/任务/通知/审计不变。
- **反例/边界**：
  - 传入 `status=RUNNING`：按 D-05，归档只接受 APPROVED；非 APPROVED 返回结构化 4xx（建议 422），不返回非 APPROVED 数据。
  - 排序未定义（TBD-08）：分页断言只看集合，不依赖顺序。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-08。

### ARCHIVE-01-b 归档组合检索：业务筛选、关键字、完成时间、发起人、流程

- **需求来源**：TEST-PLAN §6.8 ARCHIVE-01；OpenAPI `/instances/archive` 参数（status/flow_template_id/initiator_id/keyword/finished_from/finished_to/filters）；SEARCH-FILTER-PLAN“筛选 API”；PRD F8.1。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；发起人 `zhangsan`、`lisi`；流程模板 P1、P2。
  - 表单/流程：P1 表单含 `leaveType`（option）、`amount`（number）、`note`（text），配置可检索；P2 另一表单；均已发布。
  - 实例数据（均 APPROVED，完成时间可区分）：
    - I1：P1，`zhangsan`，`leaveType=年假`，`amount=500`，标题 `E2E-<runId>-A`，完成时间 T1。
    - I2：P1，`zhangsan`，`leaveType=事假`，`amount=1500`，标题 `E2E-<runId>-B`，完成时间 T2。
    - I3：P1，`lisi`，`leaveType=年假`，`amount=2500`，标题 `E2E-<runId>-C`，完成时间 T3。
    - I4：P2，`zhangsan`，`leaveType=年假`，`amount=500`，标题 `E2E-<runId>-D`，完成时间 T4。
    - 另一条 RUNNING 实例 I5：P1，`leaveType=年假`，标题 `E2E-<runId>-E`。
- **步骤**：
  1. `flow_template_id=P1` + `filters leaveType=年假`。
  2. 再加 `amount between [400,1600]`（AND）。
  3. `initiator_id=<zhangsan>` + `leaveType=年假`。
  4. `finished_from=T2`、`finished_to=T3`（取明确位于区间内的时间；边界见 TBD-09）。
  5. `keyword=E2E-<runId>-C`（标题）；再 `keyword=<I1 的实例单号>`（记录结果，不纳入通过条件，TBD-03）。
  6. E2E 在归档页组合条件并刷新，确认结果与 API 一致。
- **期望结果**：
  1. 步骤 1 → I1、I3（P1 且年假）；I4 因 P2 不命中；I5 因非 APPROVED 不命中。
  2. 步骤 2 → “年假 AND amount 400–1600”精确交集：I1 命中；I3 因 2500 不命中；I4 因 P2 不命中。断言集合 = {I1}。
  3. 步骤 3 → 仅 I1（zhangsan + 年假；I2 是事假，不命中）→ {I1}。
  4. 步骤 4 返回完成时间落在区间内的 APPROVED 实例；I5 即使时间在区间也不出现。
  5. 步骤 5 标题 `E2E-<runId>-C` 精确命中 I3；实例单号 keyword 是否命中仍待确认（TBD-03），只记录、不作为失败依据。
  6. 所有结果 `total` 与 E2E 列表一致；无 500。
  7. 数据副作用：无写入。
- **反例/边界**：
  - 只传 `finished_from` 晚于 `finished_to`：4xx，不返回 500（具体错误码见 TBD-09）。
  - 非管理员调用同一归档接口：403/404，见 ARCHIVE-01-d。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-03、TBD-08、TBD-09。

### ARCHIVE-01-c 导出与列表同口径：列完整、中文不乱码、动态字段有列、表单编号与实例单号不混用

- **需求来源**：TEST-PLAN §6.8 ARCHIVE-01“CSV 列完整（含动态字段）、中文不乱码；非管理员不可导出”；TEST-PLAN §6.8 SEARCH-01“表单编号与实例单号不混用”；需求方 2026-11-19 确认 R-02、R-03；TECH M6“UTF-8 BOM、中文表头、动态字段也有一列”；PRD F8.1；PHASE2 §2.1“展示控件不导出”。
- **优先级**：P0
- **验证层**：API（下载并解析 CSV）+ 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan`；`wangwu`。
  - 表单/流程：自建表单模板编码（表单编号）为 `E2E-S1-NO`，含文本、数字、日期、选项、附件、子表、展示控件（rich_text），以及 `auto_number` 字段 `reqNo`（实例单号）；流程单审批，发布；实例 I1/I2 审批至 APPROVED，其中 I1 通过机制 C 追加一个扩展字段（若流程支持），或使用种子中已有扩展字段实例。
  - 已配置可检索字段 `leaveType`、`amount`。
- **步骤**：
  1. 归档页设置筛选条件，记录列表 ID 集合 L。
  2. 使用同一组参数调用 `GET /instances/archive/export` 下载 CSV；检查响应头 `Content-Type`/`Content-Disposition`（若文档未定义则记录现状，TBD-07）。
  3. 以二进制读取前 3 字节确认 UTF-8 BOM；以 UTF-8 解码表头与内容。
  4. 解析 CSV 行，确认数据行集合与 L 一致（全部命中行，而非仅当前页）。
  5. 检查列：**表单编号**（模板编码 `E2E-S1-NO`）、**实例单号**（`reqNo` 值）、标题、流程、发起人、状态、完成时间；`leaveType`、`amount`；扩展字段列；展示控件列不应出现（PHASE2）。
  6. 检查中文（如“年假”“技术部”）显示正常，无乱码/问号。
  7. 检查导出说明/页面提示：注明“以 `=`、`+`、`-`、`@` 开头的单元格会加半角单引号 `'` 转义”（R-03）。
  8. E2E 点击导出，确认下载文件名可识别、文件可被 Excel/LibreOffice 打开。
- **期望结果**：
  1. 步骤 4：CSV 行数 = L 大小；导出的实例集合与列表完全一致（同筛选、全部页）。
  2. 步骤 5：关键列均存在；**表单编号列值 = `E2E-S1-NO`；实例单号列值 = `reqNo` 值**；两列不同名、不同值、不互换；扩展字段有独立列；展示控件无列。
  3. 步骤 3：BOM 为 `EF BB BF`；步骤 6 中文正常。
  4. 步骤 7：导出说明中可观察到 R-03 的转义规则说明；不能只写“已处理”而无具体规则。
  5. 步骤 8：文件可打开，无编码错误、无列错位。
  6. 数据副作用：无写入；导出不改变索引/实例/审计（若记录导出审计，按 TBD-27 处理）。
- **反例/边界**：
  - 子表字段如何导出（展平/JSON/多行）未定义（TBD-06）；本用例只断言“数据不丢失或以文档确定的形式存在”，评审前不强制某一种。
  - 空结果导出：见 ARCHIVE-01-e。
- **自动化位置**：`backend/tests/test_acceptance_search.py`（解析 CSV）；`testing/e2e/specs/search-export.spec.ts`（下载）
- **需求待确认项**：TBD-06、TBD-07、TBD-26、TBD-27。

### ARCHIVE-01-d 归档与单实例导出鉴权：非管理员不可归档；无关人员不可导出

- **需求来源**：TEST-PLAN §6.8 ARCHIVE-01“非管理员不可导出”；TECH M6“归档与导出：非管理员 403、单实例导出的可见性”；PRD §2 设计者无审批数据管理权；DEMO 步骤 9（发起人可导出自己的单据）；TECH §5.2 `get_instance(view)`。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan`（发起人）；`lisi`（参与审批人）；`zhaoliu`（设计者，非参与人）；`wangwu`（无关用户）。
  - 表单/流程：自建流程；实例 S1 由 `zhangsan` 发起、`lisi` 审批至 APPROVED；实例 S2 由 `wangwu` 发起并 APPROVED。
- **步骤**：
  1. `zhangsan`、`zhaoliu`、`wangwu` 分别调用 `GET /instances/archive` 与 `/instances/archive/export`。
  2. `zhangsan` 调用 `GET /instances/{S1}/export`。
  3. `zhaoliu`、`wangwu` 调用 `GET /instances/{S1}/export`。
  4. `lisi` 调用 `GET /instances/{S1}/export`（参与者；权限见 TBD-26）。
  5. 未认证请求调用上述导出接口。
  6. E2E：`zhaoliu` 直接打开归档页 URL。
- **期望结果**：
  1. 步骤 1：非管理员的归档列表/导出均 403/404，响应无任何实例数据/CSV；`admin` 可正常访问。
  2. 步骤 2：`zhangsan` 导出自己的 S1 → 200，CSV 含 S1（DEMO 明确）。
  3. 步骤 3：`zhaoliu`、`wangwu` → 403/404；响应体不含标题、表单值、附件名。
  4. 步骤 4：`lisi` 作为参与者是否可导出按 TBD-26；评审前只断言“若 200 则仅含 S1；若拒绝则 403/404，均不得包含 S2 或其他实例”。
  5. 步骤 5：401。
  6. 步骤 6：设计者打开归档页无数据、无“可导出”入口；页面不白屏。
  7. 数据副作用：无写入；拒绝请求不产生导出文件/审计业务动作（若审计导出按 TBD-27）。
- **反例/边界**：
  - 遍历 S1/S2 的 ID：全部返回同一类拒绝（403/404），不得通过状态码/错误信息差异枚举实例是否存在（TBD-22）。
- **自动化位置**：`testing/e2e/specs/permissions.spec.ts`；`backend/tests/test_acceptance_security.py`
- **需求待确认项**：TBD-22、TBD-26、TBD-27。

### ARCHIVE-01-e 空归档与空导出：空状态、表头/空文件、无 500

- **需求来源**：PHASE3 M11 §1.5“空状态不报错”（首页同类）；TEST-PLAN ARCHIVE-01；OpenAPI `/instances/archive/export` 200；TBD-07。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；全新重置库中无任何 APPROVED 实例（其他用例数据不共享）。
  - 表单/流程：无必须；可选创建一个无实例的已发布流程。
- **步骤**：
  1. `GET /instances/archive`。
  2. `GET /instances/archive/export`。
  3. E2E 打开归档页。
  4. 使用一个不存在的筛选组合（如 `leaveType=不存在选项`，合法字段但 0 命中）再查询/导出。
- **期望结果**：
  1. 步骤 1 → 200，`items=[]`、`total=0`，不报 500。
  2. 步骤 2 → 200，返回合法 CSV；表头是否存在按 TBD-07；文件可被解析，不得是 HTML 错误页或 500。
  3. 步骤 3：页面显示空状态文案/引导，不是空白区域，无控制台未捕获错误。
  4. 步骤 4：列表 0 条；导出同样为合法空结果。
  5. 数据副作用：无写入。
- **反例/边界**：
  - 无任何流程/表单时打开归档页：仍显示空状态，不 500（如依赖流程下拉，应显示“暂无数据”）。
- **自动化位置**：`testing/e2e/specs/search-export.spec.ts`；`backend/tests/test_acceptance_search.py`
- **需求待确认项**：TBD-07。

---

## 6. DASH-01：角色化首页

### DASH-01-a 普通用户首页：卡片、待办/我发起的预览、常用流程与跳转

- **需求来源**：PHASE3 §1.2“普通用户区块”、§1.3 `GET /dashboard/overview`、§1.5 验收；TECH M11；PRD F4.1/F3.1；TEST-PLAN DASH-01；需求方 2026-11-19 确认 R-02。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（普通用户）；`lisi`、`wangwu` 为审批人；`admin` 用于造数/核对。
  - 表单/流程：至少 3 个可发起流程（其中 8 个可用流程用于常用排序，若不足则按实际数量），均已发布且对 `zhangsan` 可发起。
  - 实例/任务数据：
    - `zhangsan` 有 6 条 PENDING 待办（来自不同流程/节点，到达时间 T1<T2<…<T6）。
    - 2 条未读抄送。
    - 3 条自己发起且 RUNNING 的实例。
    - 2 条自己发起且本月 APPROVED 的实例；另有 1 条上月 APPROVED（不计入本月）。
    - 至少 7 条“我发起的”实例（含不同状态），用于验证预览只取 5 条。
    - 8 个可发起流程中，`zhangsan` 近期的发起次数分别为 5/4/3/2/1/1/0/0。
- **步骤**：
  1. `zhangsan` 调用 `GET /dashboard/overview`；同时调用 `GET /tasks/summary` 核对。
  2. 检查 `personal` 四个计数、`todos`、`my_instances`、`quick_flows`、`admin`。
  3. E2E 登录后观察首屏卡片、待办预览、我发起的、常用流程。
  4. 点击一条待办、一条我发起的、一个常用流程。
- **期望结果**：
  1. `personal.todo=6`、`personal.cc_unread=2`、`personal.mine_running=3`、`personal.mine_finished_this_month=2`；与 `/tasks/summary` 的 `todo`/`cc_unread`/`mine_running` 一致（口径复用）。
  2. `todos` 恰 5 条，按 `arrived_at` 最近优先（T6…T2），每条含标题、**实例单号（auto_number 字段值）**、当前节点、到达时间；不含已办/取消/抄送。
  3. `my_instances` 恰 5 条，按 `updated_at` 最近优先（TBD-19），每条含标题、状态、当前节点（`current_node_names` 数组，TBD-21）、更新时间；上月已完成不在“本月”计数中。
  4. `quick_flows` 最多 6 个，按“本人最近发起次数”降序；本数据中为前 6 个（5/4/3/2/1/1）；不可发起/停用流程不出现。
  5. `admin` 为 `null`。
  6. 点击跳转：待办 → 实例详情且带该 assignment 的待办状态；我发起的 → 详情只读/当前任务视角；常用流程 → 发起页且表单/流程正确。
  7. 数据副作用：无写入。
- **反例/边界**：
  - 待办超过 5 条时只展示 5 条，但卡片计数仍为全量 6。
  - 常用流程不足 6 个时展示实际数量；并列排序见 TBD-19。
- **自动化位置**：`testing/e2e/specs/dashboard.spec.ts`；`backend/tests/test_acceptance_dashboard.py`
- **需求待确认项**：TBD-18、TBD-19、TBD-21。

### DASH-01-b 空数据首页：普通用户与管理员均不空白、不报错

- **需求来源**：PHASE3 §1.5“无待办时显示空状态而不是空白”；M11 §1.6；TEST-PLAN DASH-01“空状态不报错”；TECH M11。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：新建普通用户 `E2E-<runId>-empty`（无任何任务/实例/抄送）；`admin` 在全新重置库中（无业务实例）。
  - 表单/流程：至少 1 个可发起流程（用于“常用流程”空/非空判断）或完全没有流程；两种情形分别记录。
  - 实例数据：无。
- **步骤**：
  1. 普通用户调用 `GET /dashboard/overview`。
  2. 管理员调用同一接口。
  3. E2E 分别登录，观察首屏。
  4. 普通用户点击“发起中心”空状态入口（若有）。
- **期望结果**：
  1. 普通用户：`personal` 四项均为 0；`todos=[]`、`my_instances=[]`、`quick_flows=[]`；`admin=null`；HTTP 200。
  2. 管理员：个人区块为 0；`admin` 存在且各计数为 0、`by_flow=[]`；HTTP 200。
  3. 页面：待办区/我发起的区显示明确空状态文案与可操作入口（如“去发起”/“去工作台”），不是空白容器；无未捕获 JS 错误、无 500。
  4. 数据副作用：无写入。
- **反例/边界**：
  - 完全没有任何已发布流程时，“常用流程”显示空状态而不是报错。
  - 管理员全局概览为 0 时不得出现 `NaN`/`undefined`/负值。
- **自动化位置**：`testing/e2e/specs/dashboard.spec.ts`；`backend/tests/test_acceptance_dashboard.py`
- **需求待确认项**：TBD-18、TBD-21。

### DASH-01-c 管理员/设计者额外区块：全局概览、流程分布、管理入口；普通用户不可见

- **需求来源**：PHASE3 §1.2/§1.3“admin 字段仅管理员/设计者返回，普通用户为 null”、§1.5；TECH M11；TEST-PLAN DASH-01“普通用户/管理员/设计者区块与口径正确”；D-02。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`、`zhaoliu`（设计者、非管理员）、`zhangsan`（普通用户）。
  - 数据：已知运行中实例 4 条（分属 2 个流程模板）、今日提交 3 条、本周完成 2 条；存在若干 PENDING 指派；流程分布可计算。
  - 表单/流程：至少 2 个流程模板；已发布。
- **步骤**：
  1. 分别调用 `GET /dashboard/overview`（三个账号）。
  2. 检查 `admin` 字段与 `personal`。
  3. E2E 观察管理员首页：全局概览卡片、流程分布、管理入口。
  4. E2E 观察设计者首页：不应出现全局概览与管理入口（D-02）。
  5. 点击管理入口（表单模板、流程模板、实例台账、共享表格）。
- **期望结果**：
  1. `zhangsan`：`admin=null`，页面无全局概览/流程分布/管理入口。
  2. `admin`：`admin` 非空；`running=4`、`submitted_today=3`、`finished_this_week=2`（口径见 TBD-18）；`by_flow` 只含运行中实例按模板聚合的前 5，数量与夹具一致；`pending_backlog` 为非负整数（精确口径 TBD-18，本用例不硬编码）。
  3. `zhaoliu`：`admin=null`，页面只有个人工作台，不出现全局概览/流程分布/实例台账（D-02）。
  4. 流程分布按数量 Top 5；并列排序见 TBD-18/19；不出现实例标题、发起人等明细。
  5. 管理入口：管理员点击表单模板/流程模板/实例台账/共享表格均到达对应页面且有权限；设计者只能看到表单/流程模板，不显示实例台账（D-02）。
  6. 数据副作用：无写入。
- **反例/边界**：
  - `by_flow` 超过 5 个模板时只返回 5 个，且是数量最多的 5 个。
  - 普通用户伪造前端显示管理区块不影响接口 `admin=null`；直接调管理接口仍 403（SEC-01-d）。
- **自动化位置**：`testing/e2e/specs/dashboard.spec.ts`；`backend/tests/test_acceptance_dashboard.py`
- **需求待确认项**：TBD-18、TBD-19（按 P0-DECISIONS 默认执行）。

### DASH-01-d 首屏单次请求、10 秒轮询与“不闪烁”

- **需求来源**：PHASE3 §1.3“一次返回首页所需数据，避免首屏发 5–6 个请求”、§1.5“首页接口只发一次请求，刷新不闪烁”、§1.6“10 秒轮询刷新角标与待办预览”；PRD F7.2（≤10s 感知）；TEST-PLAN DASH-01。
- **优先级**：P0
- **验证层**：浏览器 E2E（网络记录）+ API
- **前置条件**：
  - 角色与组织：`zhangsan`（普通用户）；`lisi`（审批人）。
  - 数据：`zhangsan` 有至少 2 条待办；`lisi` 可创建新任务。
  - 浏览器：Chrome/Edge；网络面板可记录请求；时区 Asia/Shanghai。
- **步骤**：
  1. 登录后进入首页，记录所有 `/dashboard/overview` 请求。
  2. 保持页面打开 25 秒，记录轮询请求时间戳与数量。
  3. 用 `lisi` 在另一浏览器上下文给 `zhangsan` 新建一条待办；观察 `zhangsan` 首页角标/待办预览更新时间。
  4. 轮询期间用 DOM 快照/截图记录卡片与列表状态。
- **期望结果**：
  1. 首屏仅 1 次 `/dashboard/overview`（其他 `/auth/me`、`/notifications/unread-count` 等允许）；不出现 5–6 个首页数据请求并发。
  2. 25 秒内按约 10 秒间隔出现轮询请求（允许网络/调度误差；不得高频刷）；请求不导致整页 reload。
  3. 新待办在 ≤10 秒内出现在角标/待办预览（F7.2），点击可进入对应详情。
  4. 轮询期间卡片/列表不出现归零、骨架屏闪回、整块消失再出现；数值只做增量更新（“不闪烁”的判定以首屏元素持续挂载 + 无中间空态为准；TBD-20）。
  5. 数据副作用：轮询只读，无写入。
- **反例/边界**：
  - 后端短暂失败时，页面保留上一次数据并给出可恢复提示，不清空首页（故障恢复属探索式，本用例只记录）。
- **自动化位置**：`testing/e2e/specs/dashboard.spec.ts`（Playwright `page.on('request')` + 时间戳）
- **需求待确认项**：TBD-20。

### DASH-01-e 首页数据隔离：只看自己的明细，管理员只看聚合

- **需求来源**：PRD §2“实例可见性：发起人、历任/现任处理人、被抄送人、管理员可见详情；其他人不可见”；PHASE3 §1.4“不改动实例可见性规则”；TECH §5.2；TEST-PLAN DASH-01。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`、`wangwu` 各为不同实例的发起人/审批人；`admin`；`zhaoliu`（设计者，非参与人）。
  - 数据：
    - `zhangsan`：待办 2 条（实例 A、B）、我发起的 2 条（实例 C、D）、抄送 1 条（实例 E）。
    - `wangwu`：待办 1 条（实例 F）、我发起的 1 条（实例 G）。
    - `admin`：不属于上述任何实例的参与人。
- **步骤**：
  1. 分别调用三个账号的 `GET /dashboard/overview`。
  2. 检查 `todos`/`my_instances` 的实例 ID/标题集合。
  3. E2E 用 `zhangsan` 点击首页每条预览，确认只能进入自己的相关实例。
  4. 用 `zhaoliu` 观察首页：`admin=null`，不能看到任何聚合/明细（D-02）。
- **期望结果**：
  1. `zhangsan` 的 `todos` 只含 A/B（及自己的其他待办），不含 F；`my_instances` 只含 C/D/G 中自己发起的；抄送计数只算 E。
  2. `wangwu` 的预览只含 F/G，不含 A–E。
  3. `admin` 的 `admin` 聚合不含任何实例标题、发起人姓名、表单值；个人预览只含自己参与的实例（若没有则为空）。
  4. `zhaoliu` 的 `admin=null`；不得通过首页跳到 `zhangsan` 的详情（除非其为参与人）。
  5. 直接访问他人实例 ID → 403/404（SEC-01-a）。
  6. 数据副作用：无写入。
- **反例/边界**：
  - 管理员全局计数不得因为包含他人实例而在页面上列出标题；下拉/悬浮不得泄露标题。
- **自动化位置**：`testing/e2e/specs/dashboard.spec.ts`；`backend/tests/test_acceptance_dashboard.py`
- **需求待确认项**：TBD-21（按 OpenAPI 默认执行）。

---

## 7. SEC-01：访问控制、IDOR 与角色越权

### SEC-01-a 实例 IDOR：无关用户/设计者遍历 render/progress/timeline/snapshot/export

- **需求来源**：TEST-PLAN §10.1“IDOR：实例、附件、任务、模板、审计、导出接口逐一用无关用户 ID 访问”；PRD §2 可见性；TECH §5.2 `get_instance(view)`；TEST-PLAN PERM-03；TBD-22。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人，参与实例 S）、`lisi`（审批人，参与 S）、`wangwu`（无关用户）、`zhaoliu`（设计者，非参与人）、`admin`。
  - 表单/流程：自建流程；实例 S 由 `zhangsan` 发起，当前在 `lisi` 待办；实例数据含标题、表单值、附件。
  - 另有一条无关实例 S2 属于 `wangwu`，用于 ID 遍历。
- **步骤**：
  1. `wangwu` 依次调用 `GET /instances/{S}/render`、`/progress`、`/timeline`、`/snapshots/diff`、`/snapshots/{sid}`、`/export`。
  2. `zhaoliu` 重复上述调用。
  3. `lisi`（参与人）调用 `/render`、`/timeline`。
  4. `admin` 调用 `/render`。
  5. E2E：`wangwu` 直接打开 `/instance/{S}` 的 URL；再尝试 `/instance/{S2}` 自己的实例作为对照。
  6. 遍历连续实例 ID（S-1、S+1 等），记录状态码与响应体。
- **期望结果**：
  1. 步骤 1/2：所有接口均 403/404；响应体不含标题、表单值、附件名、时间线、进度节点名、发起人姓名；各接口错误形状一致，不泄露内部异常。
  2. 步骤 3：参与人 200，能看到与自身权限匹配的内容（hidden 字段仍不可见，见 SEC-02-a）。
  3. 步骤 4：管理员 200。
  4. 步骤 5：无关用户页面显示无权限/未找到，不渲染任何表单数据；自己的 S2 正常。
  5. 步骤 6：他人 ID 全部拒绝，不得返回“存在但无权”与“不存在”两种可区分文案（统一 403/404 策略，TBD-22）。
  6. 数据副作用：无写入；拒绝请求不产生业务动作/通知/审计动作。
- **反例/边界**：
  - 仅改 URL 中的 `assignment_id` 也见 SEC-01-b；仅改 `snapshot_id` 也不得绕过实例可见性。
- **自动化位置**：`testing/e2e/specs/permissions.spec.ts`；`backend/tests/test_acceptance_security.py`
- **需求待确认项**：TBD-22。

### SEC-01-b 任务/指派 IDOR：非指派人不能查看、处理、转办或取退回目标

- **需求来源**：TEST-PLAN §10.1 IDOR（任务）；TECH §5.2 `get_instance(act)`“assignment 属己且 PENDING”；PRD §3.5.2；M14 转办规则；TEST-PLAN TASK-06/PERM-03。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（当前指派人）、`wangwu`（无关用户）、`zhaoliu`（设计者）、`admin`。
  - 表单/流程：自建流程，实例 S 当前节点指派人 `lisi`，且存在一个退回目标配置。
  - 数据：`lisi` 有 PENDING assignment A1；`wangwu` 的 assignment 属于另一实例。
- **步骤**：
  1. `wangwu` 调 `GET /tasks/assignments/{A1}`、`GET /tasks/assignments/{A1}/return-targets`、`POST /tasks/assignments/{A1}/act`、`POST /tasks/assignments/{A1}/transfer`。
  2. `zhangsan`（发起人但非指派人）调用 `/act`。
  3. `zhaoliu`（非参与人设计者）调用 `/act`。
  4. `lisi` 先合法同意一次；随后再次调用 `/act`（重复处理）。
  5. 每次拒绝后，用 `admin` 读取实例状态/任务数/时间线，对比拒绝前。
- **期望结果**：
  1. 步骤 1–3：全部 403/404；响应体不含任务意见、表单数据、实例标题；`act` 不改变实例状态/任务/快照/通知。
  2. 步骤 4：第一次 200；第二次 409/422（或幂等返回既有结果，TBD-30），但**不得**产生第二次动作/快照/通知，不得把任务再次置为已完成。
  3. 步骤 5：所有拒绝请求前后，实例状态、PENDING/DONE/CANCELLED 计数、时间线条数、快照数、通知数完全一致。
  4. 不存在“非指派人 act 成功后任务仍显示待办”或“任务被取消但实例卡住”的中间态。
- **反例/边界**：
  - 管理员对他人的待办执行 `act`：文档未授予管理员代审批权（TECH 事件表 `TERMINATE` 是管理员动作，`act` 要求 assignment 属己）；本用例按“管理员也不得 act”断言；若产品确认管理员可代办，需另行定义并更新（TBD-29）。
  - 转办目标人不能是同任务已有待办的人（M14），见 CONC/转办专项；本用例只验证无关人转办被拒。
- **自动化位置**：`backend/tests/test_acceptance_security.py`；`testing/e2e/specs/permissions.spec.ts`
- **需求待确认项**：TBD-22、TBD-29、TBD-30。

### SEC-01-c 附件下载鉴权：未认证、无关人、临时附件、绑定后的参与者

- **需求来源**：TEST-PLAN §10.1“附件：白名单、大小、路径穿越、临时附件绑定、下载鉴权”；PERM-04“上传者/管理员/实例参与者可下载；无关人员不可；提交/审批后临时附件绑定实例”；TECH M6“下载权限 = 上传者 / 管理员 / 所属实例参与者”；需求方 2026-11-19 确认 R-04（抄送人附件跟随字段权限，专项见 SEC-02-f）；TBD-24。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（上传者/发起人）、`lisi`（审批人/参与者）、`wangwu`（无关用户）、`zhaoliu`（设计者非参与人）、`admin`。
  - 数据：`zhangsan` 上传临时附件 F1（未绑定实例）；提交实例 S 时携带 F1，F1 绑定 S；另上传 F2 未绑定且不提交；实例 S 当前在 `lisi` 待办。
- **步骤**：
  1. 未认证 `GET /files/{F1}/download`。
  2. 绑定前：`lisi`、`wangwu`、`zhaoliu` 分别下载 F1（此时 F1 仍为 TEMP 或刚上传未提交；需在提交前执行）。
  3. `zhangsan` 提交 S（携带 F1）；`admin` 确认 F1 已绑定 S。
  4. 绑定后：`lisi`、`wangwu`、`zhaoliu`、`admin` 分别下载 F1；`zhangsan` 下载 F1。
  5. 尝试下载 F2（未绑定、未提交）：`wangwu`、`lisi`、`admin`。
  6. 调用 `GET /files/{id}` 元数据接口，重复上述角色组合。
  7. E2E：在实例详情点击附件下载（`lisi` 与 `wangwu` 各一次）。
- **期望结果**：
  1. 步骤 1 → 401，不返回文件内容/文件名。
  2. 步骤 2：`zhangsan`/`admin` 200；`lisi`（尚未绑定）403/404；`wangwu` 403/404；`zhaoliu` 403/404。
  3. 步骤 4：`lisi`（参与者）200；`zhangsan`（上传者）200；`admin` 200；`wangwu` 403/404；`zhaoliu` 403/404。
  4. 步骤 5：F2 未绑定，`wangwu`/`lisi` 403/404；`admin` 按技术设计“管理员可下载”应 200（TBD-24 若改为仅上传者，则以评审为准）。
  5. 步骤 6：元数据接口与下载接口权限一致；拒绝响应不含文件名/大小/上传者等敏感元数据。
  6. 步骤 7：`lisi` 可下载并得到与上传内容一致的字节；`wangwu` 页面无下载入口/被拒绝，不泄露 object URL。
  7. 数据副作用：下载为只读；不改变附件绑定/实例/通知/审计动作。
- **反例/边界**：
  - 遍历附件 ID：无关 ID 全部统一拒绝；不得通过“404 vs 403”推断附件是否存在（TBD-22）。
  - 路径穿越文件名见 SEC-02-e；本用例使用正常文件名。
  - 抄送人（非审批参与者）的附件可见性不按“参与者”一刀切，而按字段权限：见 SEC-02-f。本用例只验证上传者/参与者/管理员/无关人。
- **自动化位置**：`backend/tests/test_acceptance_security.py`；`testing/e2e/specs/permissions.spec.ts`
- **需求待确认项**：TBD-22、TBD-24、TBD-26。

### SEC-01-d 角色越权与模板 IDOR：普通用户/设计者不能进入对方管理面

- **需求来源**：PRD §2 角色权限“设计者无审批数据管理权”；TECH §5.2 `AdminUser`/`DesignerUser`；TEST-PLAN §10.1“角色越权：普通用户/设计者访问管理员接口；设计者查看审批数据”；TECH M5“设计者非相关人 403”；TBD-23。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（普通用户）、`zhaoliu`（设计者，非管理员）、`admin`。
  - 数据：至少 1 个表单模板、1 个流程模板、1 个他人实例 S（`zhangsan` 发起、`lisi` 审批）、1 条审计记录；S 未结束。
- **步骤**：
  1. `zhangsan` 调用设计端接口：`GET/POST /form-templates`、`POST /form-templates/{id}/versions`、`POST /form-versions/{vid}/validate|publish`、`GET/POST /flow-templates`、`POST /flow-versions/{vid}/publish`、`PUT /form-templates/{id}/search-fields`。
  2. `zhangsan` 调用管理端接口：`GET/POST /users`、`/departments`、`/roles`、`GET /admin/audit-logs`、`POST /instances/{S}/terminate`、`POST /instances/{S}/ext-fields`。
  3. `zhaoliu` 调用管理端接口（同上用户/部门/角色/审计/终止）。
  4. `zhaoliu` 调用 `POST /instances/{S}/ext-fields`（非参与人）；再调用 `GET /instances?scope=all`、`GET /instances/archive`。
  5. `zhaoliu` 调用设计端接口创建/发布一个表单与流程。
  6. `zhangsan` 调用 `GET /instances/start-options/{flow_template_id}`（应允许的发起页元数据）。
- **期望结果**：
  1. 步骤 1：所有设计端接口 403/404；不返回模板 schema、版本内容。
  2. 步骤 2：所有管理端接口 403/404；不返回用户/部门/角色/审计数据；终止/追加字段不改变 S。
  3. 步骤 3：设计者同样被管理端拒绝；设计者不是管理员。
  4. 步骤 4：对非参与实例追加字段 → 403/404，S 不被修改；`scope=all`/归档 → 403/404（D-02：设计者无审批数据管理权，不给只读聚合）。
  5. 步骤 5：设计者可以创建/发布表单与流程（DesignerUser 允许），操作成功并写审计/版本记录。
  6. 步骤 6：普通用户可获取自己可发起流程的发起页元数据（这是发起所需），不视为越权；不得借此获取他人实例数据。
  7. 数据副作用：所有拒绝请求无写入；设计者合法发布只影响模板版本。
- **反例/边界**：
  - `zhaoliu` 作为 S 的参与人时，可以查看 S（可见性按参与关系，而不是设计者角色）；设计者角色本身不扩大实例可见范围。
  - 普通用户直接读取已发布模板版本的接口是否允许见 TBD-23（按 P0-DECISIONS 默认：普通用户只能通过发起页元数据读取，不直接读版本内容）；本用例把“设计端管理接口”与“发起页元数据”分开断言。
- **自动化位置**：`backend/tests/test_acceptance_security.py`；`testing/e2e/specs/permissions.spec.ts`
- **需求待确认项**：TBD-23、TBD-24（按 P0-DECISIONS 默认执行）。

### SEC-01-e 审计与导出 IDOR：普通用户/设计者不可读审计、不可越权导出

- **需求来源**：TEST-PLAN §10.1“IDOR：…审计、导出接口”；PRD F6.6 操作审计查询（P1，但接口已存在）、F8；TECH M6“非管理员 403”；TBD-27。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin`、`zhangsan`（普通用户）、`zhaoliu`（设计者）、`wangwu`（无关用户）。
  - 数据：存在审计记录（组织/模板/实例动作至少各 1 条）；存在 APPROVED 实例 S1（`zhangsan` 发起）与 S2（`wangwu` 发起）；存在运行中实例 S3。
- **步骤**：
  1. `zhangsan`、`zhaoliu` 分别调用 `GET /admin/audit-logs` 与 `/admin/audit-logs/export`。
  2. `zhangsan`、`zhaoliu` 调用 `GET /instances/archive` 与 `/instances/archive/export`。
  3. `wangwu` 调用 `GET /instances/{S1}/export`；`zhaoliu` 同样。
  4. `zhangsan` 调用 `GET /instances/{S3}/export`（自己的运行中实例）。
  5. `admin` 调用上述管理员接口作为正例。
- **期望结果**：
  1. 步骤 1：普通用户/设计者均 403/404；响应无审计条目、无 CSV、不泄露操作人/IP/业务对象名称。
  2. 步骤 2：普通用户/设计者均 403/404；无归档数据。
  3. 步骤 3：`wangwu` 与 `zhaoliu` 对 S1 的导出 403/404，不泄露标题/表单值。
  4. 步骤 4：`zhangsan` 对自己运行中实例的导出——若接口允许，则不得包含尚未揭晓的 hidden 字段值（SEC-02-a/b）；若拒绝，403/404 也可接受。两种结果都必须无越权数据。
  5. 步骤 5：`admin` 正常获得审计/归档数据；审计导出内容与列表筛选一致。
  6. 数据副作用：无写入；拒绝请求不产生导出文件、不写业务审计（如系统记录安全审计，则另计）。
- **反例/边界**：
  - 用 `biz_id`/`actor_id`/`keyword` 参数尝试枚举他人审计：仍只返回管理员权限范围内的数据；非管理员直接 403。
  - 审计日志不可被删除/修改：不存在对应写接口（405/404），本用例只记录。
- **自动化位置**：`backend/tests/test_acceptance_security.py`
- **需求待确认项**：TBD-22、TBD-26、TBD-27。

---

## 8. SEC-02：字段泄露、富文本 XSS、CSV 注入与附件内容安全

### SEC-02-a hidden 字段泄露：渲染、快照、时间线、打印、伪造提交

- **需求来源**：TEST-PLAN PERM-02“hidden 字段不出现在响应、快照、导出、打印中；伪造提交值被过滤”；PRD §3.4 机制 A/示例二“申请人全程看不到实际核销金额”；TECH §4.5；TEST-PLAN §10.1；需求方确认 D-04。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（部门经理）、`wangwu`（财务填写人）、`admin`。
  - 表单/流程：自建表单含 `actualAmount`（number）、`invoiceNo`（text），`visible_at_start=false`；流程：部门经理审批（这两个字段 hidden）→ 财务填写节点（`actualAmount`/`invoiceNo` editable-required）→ 结束；发布。
  - 实例状态：`zhangsan` 提交实例 S（表单其余字段合法），当前在 `lisi` 节点；两个 hidden 字段均未填写。
- **步骤**：
  1. `zhangsan` 在发起页/提交前检查两个字段是否渲染；提交时在请求 `data` 中伪造 `actualAmount=999`、`invoiceNo="FAKE"`。
  2. 提交后，`zhangsan` 调 `GET /instances/{S}/render`、`/timeline`、`/snapshots/{sid}`；检查表单值、权限、快照。
  3. `lisi` 调 `/render`（部门经理视角）。
  4. `lisi` 尝试用 `act` 的 `field_patch` 修改 `actualAmount`（该节点无编辑权）。
  5. `wangwu` 在财务节点打开 `/render`，确认字段可编辑；填写 `actualAmount=500`、`invoiceNo="INV-1"` 并提交。
  6. `zhangsan` 在实例结束前打开详情/打印预览；结束后再打开详情与导出。
  7. 检查通知/时间线文本是否出现 999/500（在未揭晓阶段）。
- **期望结果**：
  1. 步骤 1：发起页不渲染这两个字段（hidden 不出现编辑控件）；提交请求中的伪造值被服务端过滤——实例 `current_data` 不包含 999/FAKE（以 `zhangsan` 后续 render 与财务节点 render 的值可观察）。
  2. 步骤 2/3：`zhangsan` 与 `lisi` 的 render/timeline/snapshot 响应中，`actualAmount`/`invoiceNo` 的值不存在；权限为 hidden 或字段不在可见视图；打印预览不出现该字段/值。
  3. 步骤 4：`lisi` 的非法 `field_patch` → 422 或被忽略；`actualAmount` 仍为空，快照数不增加。
  4. 步骤 5：`wangwu` 可见且必填，填写后成功；其他节点的用户仍不可见（直到归档）。
  5. 步骤 6：实例结束前，`zhangsan` 的详情/打印/导出不出现 500/INV-1 或伪造值；实例结束后（APPROVED）按 TECH §4.5 归档视角可见且只读，值恰为 500/INV-1。
  6. 步骤 7：未揭晓阶段的任何通知/时间线文本不含 hidden 值；审计 diff 若记录该字段，仅对有权者可见（按 TBD-27）。
  7. 数据副作用：伪造值未落库；合法值只在财务节点写入一次，快照/审计/字段来源追踪一致。
- **反例/边界**：
  - 通过导出、打印、搜索筛选三种旁路尝试读取 hidden 值：分别见 SEC-02-b、SEC-02-c 与打印断言。
  - `visible_at_start=false` 的字段在“发起页预览/设计器预览”中设计者可见是配置视角，不属于实例数据泄露；本用例只验证运行时实例。
- **自动化位置**：`backend/tests/test_acceptance_security.py`；`testing/e2e/specs/permissions.spec.ts`
- **需求待确认项**：TBD-25、TBD-27（默认）。

### SEC-02-b hidden 字段不能通过检索元数据/筛选/导出推断

- **需求来源**：SEARCH-FILTER-PLAN“scope=mine：非管理员只返回 start_visible=True…防止通过筛选推断隐藏补充字段”“归档业务筛选仅管理员”；TEST-PLAN PERM-02/SEARCH-01；TECH §4.5 L5；TBD-29（默认）。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（普通用户/发起人）、`zhaoliu`（设计者）、`admin`、`wangwu`（财务填写人）。
  - 表单/流程：同 SEC-02-a 的隐藏补充字段，已配置为可检索；流程：部门经理 → 财务填写 → 结束。
  - 实例状态：S 运行中，财务节点已填写 `actualAmount=500`；S2 未填写（空）。
- **步骤**：
  1. `zhangsan` 调 `GET /instances/search-fields?flow_template_id=<id>&scope=mine`。
  2. `zhangsan` 用 `filters` 对 `actualAmount` 做 `eq 500`、`is_empty`、`gte 0` 三种请求。
  3. `zhangsan` 用 `filters` 对一个不存在的字段 `no_such_field` 做同样请求，比较状态码/响应体。
  4. `zhaoliu` 调 `scope=archive` 的 search-fields（非管理员）。
  5. `admin` 调 `scope=archive` 的 search-fields 与归档筛选。
  6. `zhangsan` 调单实例导出（若允许）并检查 CSV。
- **期望结果**：
  1. 步骤 1：元数据不包含 `actualAmount`（或明确 `selected=false` 且不可选）；不含其选项/值；`start_visible=true` 的字段仍在。
  2. 步骤 2：三种请求均 422；错误体不包含 500、字段选项或“字段存在”的可区分提示。
  3. 步骤 3：隐藏字段与未知字段的拒绝方式一致（均为 422，错误码/文案不暴露字段存在性；若文档要求区分，按 TBD-16 更新）。
  4. 步骤 4：设计者访问归档 search-fields → 403/404（归档筛选仅管理员）。
  5. 步骤 5：管理员归档元数据可包含 `actualAmount`（终态可见，D-04）；筛选 `eq 500` 可命中；这是管理员权限内的合法行为。
  6. 步骤 6：若发起人可导出运行中实例，CSV 不含 500；若不可导出，403/404 也可接受；两种都不得泄露 hidden 值。
  7. 数据副作用：无写入。
- **反例/边界**：
  - 通过反复尝试选项值/时间差异做盲推断：错误响应时间不应有可测量差异（不作为 P0 硬性门槛，记录）。
  - 设计者即使能配置字段，也不能读取实例值（SEC-01-d）。
- **自动化位置**：`backend/tests/test_acceptance_security.py`
- **需求待确认项**：TBD-16、TBD-26、TBD-29（默认）。

### SEC-02-c 富文本 XSS：脚本、事件属性、危险协议在预览/详情/打印中被清洗

- **需求来源**：TEST-PLAN §10.1“富文本 XSS：Markdown 白名单；脚本/事件属性/危险协议被清洗”；PHASE2 §2.1“受限 Markdown；前后端白名单清洗，禁止任意 HTML”；TECH M8；TBD-25。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhaoliu`（设计者）、`zhangsan`（发起人）、`admin`。
  - 表单/流程：自建表单含一个 `rich_text` 展示控件，`display.markdown` 包含以下载荷（可分批）：
    - `<script>window.__xss=1</script>`
    - `<img src=x onerror="window.__xss=2">`
    - `[点我](javascript:window.__xss=3)`
    - `<iframe src="javascript:window.__xss=4"></iframe>`
    - `<svg onload="window.__xss=5"></svg>`
    - 正常 Markdown：`**加粗**`、`[合法链接](https://example.com)`。
  - 流程：单审批节点，发布；实例 S 运行中。
- **步骤**：
  1. 设计者保存并发布表单；若保存/发布被拒绝，记录错误信息（不允许“拒绝”以外的静默丢弃）。
  2. 调用 `POST /form-versions/{vid}/preview`，检查返回的预览 schema/HTML 是否含危险片段。
  3. 发起页/实例详情页打开 S，设置 `window.__xss` 监听（Playwright `page.addInitScript` 设哨兵）；等待渲染完成。
  4. 点击富文本中的链接；触发图片加载错误；检查 DOM 中是否存在 `<script>`、`onerror`/`onload` 属性、`javascript:` href。
  5. 打开打印预览；检查打印文档同样不含危险节点。
  6. 用 `admin` 打开同一实例归档视图，重复步骤 3–5。
- **期望结果**：
  1. 正常 Markdown 渲染为加粗/可点击的 https 链接；危险载荷不作为可执行 HTML 生效。
  2. `window.__xss` 始终为 `undefined`；无 alert/dialog；无向 `javascript:`/`data:` 的导航请求。
  3. DOM 中不存在来自载荷的 `<script>`/`<iframe>`/`<svg onload>` 可执行节点；不存在 `onerror`/`onload` 内联事件属性；`javascript:` 链接被移除或替换为安全文本。
  4. 后端 preview 响应中不含可直接执行的脚本/事件属性；若后端在发布时拒绝危险内容，必须给出明确 422，且不影响已有草稿/版本。
  5. 打印预览/归档视图与详情页使用同一清洗结果，不存在“详情安全、打印泄露”的旁路。
  6. 数据副作用：危险配置不写入已发布 schema（或写入后被渲染层清洗）；正常内容不被破坏。
- **反例/边界**：
  - 大小写/编码变体（`JaVaScRiPt:`、HTML 实体、`<scr<script>ipt>`）同样不得执行；至少覆盖 3 种变体。
  - 图片地址 `data:image/svg+xml` 是否允许见 TBD-25；本用例要求不允许执行脚本。
- **自动化位置**：`testing/e2e/specs/security.spec.ts`；`backend/tests/test_acceptance_security.py`
- **需求待确认项**：TBD-25。

### SEC-02-d CSV 公式注入：= + - @ 前缀统一加半角单引号

- **需求来源**：TEST-PLAN §10.1“CSV 注入”；需求方 2026-11-19 确认 R-03；TECH M6 CSV 导出。
- **优先级**：P0
- **验证层**：API（解析 CSV）+ 手工/脚本打开电子表格
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan` 发起。
  - 表单/流程：自建表单含文本字段 `subject`、多行 `note`、扩展字段（若可用）；实例 I1–I4 审批至 APPROVED，另有一条正常文本对照实例 I5。
  - I1–I4 的数据（均为文本）：I1 `subject="=1+1"`、`note="+SUM(A1:A2)"`；I2 `subject="-1+1"`；I3 `subject="@SUM(A1)"`；I4 `subject="正常文本"`。Tab/CR 前缀另建观察样本，但不属于 R-03 的通过条件。
- **步骤**：
  1. `admin` 导出归档 CSV（包含上述实例）。
  2. 用文本编辑器/CSV 解析器读取 I1–I3 的原始单元格内容，逐字符检查前缀。
  3. 用 Excel/LibreOffice 打开 CSV（或自动化公式扫描器），观察单元格显示值与是否出现计算/错误值（`#NAME?`/`#VALUE!`）或外部链接请求。
  4. 对单实例导出重复步骤 1–3（若该实例包含危险值）。
  5. 检查导出说明/页面提示是否注明 R-03 规则。
  6. 检查 UI 列表/详情中这些值仍按原文显示。
  7. 观察 tab/CR 前缀样本的实际处理，记录但不作为通过/失败条件。
- **期望结果**：
  1. 原始 CSV 中，以 `=`、`+`、`-`、`@` 开头的单元格**各有一个半角单引号 `'` 前缀**，即 `'=1+1`、`'+SUM(A1:A2)`、`'-1+1`、`'@SUM(A1)`；转义字符紧贴原值，不吞掉原字符。
  2. 用 Excel/LibreOffice 打开后，单元格显示原文本 `=1+1`、`+SUM(A1:A2)`、`-1+1`、`@SUM(A1)`；不执行公式、不出现 `#NAME?`/`#VALUE!`、不发起外部链接请求。
  3. 正常文本 I4 不受影响，无多余前缀。
  4. 步骤 5：导出说明/页面提示中可观察到“以 `= + - @` 开头加单引号 `'`”的说明。
  5. 步骤 6：列表/详情 UI 仍显示原始文本，不因导出转义而改变业务数据。
  6. 步骤 7：tab/CR 前缀的处理只记录；若产品后续将其纳入规则，再更新本用例。
  7. 数据副作用：导出只读；不改变实例数据。
- **反例/边界**：
  - 仅用双引号包裹 `"=1+1"` 不足以防止 Excel 解释；不得把“加了引号”当作通过。
  - 前缀后是公式/命令文本时，同样必须显示为文本；不得只对 `=` 处理而漏掉 `+`、`-`、`@`。
  - 审计导出若包含用户输入文本，是否同样转义见 TBD-27（审计范围）。
- **自动化位置**：`backend/tests/test_acceptance_security.py`（原始 CSV 断言）；`testing/e2e/specs/search-export.spec.ts`（下载）
- **需求待确认项**：TBD-27（审计导出范围；CSV 转义规则本身已确认）。

### SEC-02-e 附件上传内容安全：未认证、类型/大小、路径穿越、image_only

- **需求来源**：TEST-PLAN §10.1“附件：白名单、大小、路径穿越、临时附件绑定”；TECH M2 测试“白名单、大小限制、图片校验、越权下载、存储隔离”；TBD-24。
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（普通用户）、`admin`；未认证客户端。
  - 环境：独立附件目录（`STORAGE_ROOT` 指向测试临时目录）；记录操作前后目录文件快照（路径/文件名/数量）。
  - 文件样本：允许类型样本（按 TBD-24 评审白名单，选一个明确允许的类型）；`.exe`、`.html`、`.svg`（若不在白名单）、超过大小上限的文件、`image_only` 用的文本文件；文件名含 `../../evil.txt`、`..\\evil.txt`、绝对路径、NUL/控制字符。
- **步骤**：
  1. 未认证调用 `POST /files/upload`。
  2. `zhangsan` 上传允许类型样本；再上传 `.exe`/`.html`/`.svg`。
  3. 上传超过大小上限的文件；调用 `POST /files/upload?image_only=true` 上传文本文件。
  4. 使用路径穿越文件名上传；检查响应中的文件名、存储目录快照。
  5. 下载上传成功的文件，检查 `Content-Disposition`/`Content-Type`；不通过 API 直接猜测存储 URL 访问。
- **期望结果**：
  1. 步骤 1 → 401，不写文件。
  2. 步骤 2：允许类型 200；白名单外类型 → 4xx，明确提示类型不允许；不写文件。
  3. 步骤 3：超限 → 4xx（413 或 422），不写文件；`image_only` 非图片 → 4xx。
  4. 步骤 4：上传成功时响应文件名被清理，不含路径分隔符/`..`；存储目录中不出现目标目录之外的新文件；失败时 4xx 且无文件写入。
  5. 步骤 5：下载响应的 `Content-Disposition` 为 attachment 或安全文件名；不允许被浏览器当作可执行 HTML/脚本内联渲染（若白名单允许 HTML/SVG，则必须强制下载并清洗，TBD-24）。
  6. 数据副作用：只有合法上传创建附件元数据/文件；失败上传不留下孤儿记录/文件。
- **反例/边界**：
  - 双扩展名（`a.jpg.exe`）、大小写绕过（`.EXE`）、MIME 伪造：均按白名单拒绝或安全存储；至少覆盖 2 种。
  - 临时附件未绑定前的下载权限见 SEC-01-c。
- **自动化位置**：`backend/tests/test_acceptance_security.py`
- **需求待确认项**：TBD-24。

### SEC-02-f 抄送人附件跟随字段权限：可见字段可下载，hidden 字段及附件不可见

- **需求来源**：需求方 2026-11-19 确认 R-04；TEST-PLAN §10.1“附件下载鉴权”；PERM-04“上传者/管理员/实例参与者可下载；无关人员不可”；TECH M6“下载权限 = 上传者 / 管理员 / 所属实例参与者”；PRD F7 抄送与可见性。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人/参与者）、`wangwu`（抄送人，非审批人）、`admin`。
  - 表单/流程：自建表单含两个附件字段：`invoice`（抄送人可见）与 `internalMemo`（抄送人 hidden，审批人/管理员可见）；流程：`lisi` 审批节点 → 抄送 `wangwu`；发布。
  - 实例状态与数据：`zhangsan` 上传 `invoice.pdf` 到 `invoice`；`lisi` 在审批节点上传 `internal-memo.pdf` 到 `internalMemo`；实例审批通过并完成抄送，`wangwu` 有抄送记录。
- **步骤**：
  1. `wangwu` 调 `GET /instances/{S}/render`，检查两个附件字段与文件名。
  2. `wangwu` 下载 `invoice` 附件；比对字节与上传文件。
  3. 由 `admin` 取得 `internalMemo` 的附件 ID；`wangwu` 直接调用下载与元数据接口。
  4. `wangwu` 打开时间线、打印预览、单实例导出（若允许），检查 `internalMemo` 是否出现。
  5. `lisi`、`admin` 分别下载 `internalMemo` 作为正例对照。
  6. `wangwu` 遍历相邻附件 ID，记录状态码与响应体。
- **期望结果**：
  1. 步骤 1：`wangwu` 的 render 中 `invoice` 字段可见、附件文件名/元数据存在；`internalMemo` 字段、文件名、附件 ID 均不出现（hidden 字段连字段名都不展示）。
  2. 步骤 2：`invoice` 下载 200，字节与 `invoice.pdf` 一致。
  3. 步骤 3：`internalMemo` 下载与元数据接口均 403/404；响应不含文件名、大小、上传者、MIME。
  4. 步骤 4：时间线/打印/导出中不出现 `internalMemo` 的文件名或内容；`invoice` 按可见字段规则出现（导出是否含附件列见 TBD-26）。
  5. 步骤 5：`lisi`/`admin` 下载 `internalMemo` 200（有权者正例），确认附件本身未损坏。
  6. 步骤 6：相邻附件 ID 全部同一种拒绝方式，不得通过 403/404 差异推断 hidden 附件是否存在。
  7. 数据副作用：所有下载为只读；不改变附件绑定、实例、通知、审计业务动作。
- **反例/边界**：
  - 抄送人同时是审批人时，按审批人字段权限判定（应以更宽的合法权限为准）；本用例的 `wangwu` 仅是抄送人。
  - 可见字段的附件由他人上传（如 `lisi` 上传到 `invoice`）时，抄送人仍可下载；字段权限而非上传者身份决定可见性。
  - hidden 字段的附件即使知道 ID 也不可下载；仅隐藏文件名不足以通过。
- **自动化位置**：`backend/tests/test_acceptance_security.py`；`testing/e2e/specs/permissions.spec.ts`
- **需求待确认项**：TBD-22（统一拒绝码）、TBD-24（其他附件策略）、TBD-26（单实例导出范围）。

---

## 9. CONC-01：并发、幂等与唯一结果

> 并发用例均使用独立实例/独立数据库夹具；每个用例重复执行 N 次（建议 20 次，若时间有限至少 10 次），每次从新建实例开始，不共享可变数据。**通过条件看最终不变量，不看哪个请求“赢”**；输家允许 409/422，但不允许出现重复任务、覆盖、卡死。

### CONC-01-a 重复提交/双击/多标签：只产生一个实例与一套任务

- **需求来源**：PRD §3.5.2“均要求幂等”；§7“审批动作幂等；并发提交不产生重复任务”；TECH §3.4“HTTP 重放 request_id 唯一索引；派发幂等”；TEST-PLAN TASK-06/INIT-03；TBD-30。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）；`lisi`（首节点审批人）。
  - 表单/流程：自建表单（必填字段齐全）与单审批节点流程，发布；`zhangsan` 已保存草稿 D。
  - 数据：无已提交实例；记录提交前任务数/通知数。
- **步骤**：
  1. 对 D 同时发出两个 `POST /instances/{D}/submit`（同一 `X-Request-Id`）。
  2. 另建草稿 D2，同时发出两个 submit（**不同** `X-Request-Id`）。
  3. E2E 双击提交按钮；另开两个标签页同时提交同一草稿。
  4. 查询“我发起的”列表、`lisi` 的待办、实例数、任务数、快照数、通知数。
  5. 对已驳回实例做两次并发 `resubmit`；检查轮次与任务。
- **期望结果**：
  1. 步骤 1：两个响应均为成功/幂等结果（200 或 409，TBD-30），但系统中只存在**一个**实例、一个 round=1、一套首节点任务；每个审批人只有一条待办。
  2. 步骤 2：即使 request_id 不同，状态机/唯一约束保证仍只有一个实例/一套任务；第二个请求不得创建第二个实例。
  3. 步骤 3：UI 双击/多标签只得到一个实例；页面最终进入同一详情页；不出现两个“提交成功”实例。
  4. 步骤 4：快照数/提交动作数各 1；每个接收人通知恰好 1 条（`dedup_key` 生效）；待办数 1/人。
  5. 步骤 5：轮次只 +1，重提只生成一套新任务；旧轮任务状态为取消/已完成，不残留 PENDING。
  6. **不允许的副作用**：两个实例、重复任务、重复通知、同一实例两套并行首节点任务、流程卡死无 PENDING/DONE、500。
- **反例/边界**：
  - 网络重试（同一请求体、同一 request_id）在 1 分钟后重放：仍只产生一次效果，返回既有结果。
  - 两个不同用户同时提交同一草稿（若可见性本应阻止）→ 一个成功、一个 403/404/409，且只有一个实例。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`；`testing/e2e/specs/concurrency.spec.ts`
- **需求待确认项**：TBD-30。

### CONC-01-b 会签组同时“一人同意、一人驳回”：整单 REJECTED，且无残留/重复

- **需求来源**：PRD §3.5.3“会签 all：任一子任务驳回 → 组失败，取消其余子任务，按驳回策略处理整实例”；§9 场景二；TECH §4.3 `REJECT`；TEST-PLAN TASK-03/TASK-06；TBD-31。
- **优先级**：P0
- **验证层**：API（并发请求）
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`（会签人 1/2）、`admin`。
  - 表单/流程：自建流程含一个并行会签节点（mode=all，成员 `lisi`、`wangwu`），发布；实例 S 已提交，当前在该会签节点，两人各有 PENDING assignment。
  - 每次迭代新建 S；记录提交后任务/通知/快照基线。
- **步骤**：
  1. 使用同步屏障（两个并发 HTTP 请求在近似同一时刻发出）：`lisi` 发 `AGREE`，`wangwu` 发 `REJECT`。
  2. 等待两个响应与后台事务完成；读取实例状态、任务/指派状态、时间线、快照、通知。
  3. 重复 20 次（每次新实例）。
  4. 变体：两人同时 `AGREE`（全部同意）。
- **期望结果**：
  1. 最终实例状态**必须**为 REJECTED；不得为 APPROVED、RUNNING 或“部分完成”。
  2. 会签组内所有 assignment 不再 PENDING：同意的保留 DONE（若先成功），其余取消；驳回者记录一次 REJECT；不存在“组仍 OPEN 但无人可处理”。
  3. 时间线/快照顺序可解释：不会同时出现“会签通过/流程继续”和“实例已驳回”；快照 seq 单调；不重复。
  4. 通知：不出现“审批通过/流程完成”的误导通知；驳回/取消通知与最终状态一致；每个接收人对应事件至多一条（幂等）。
  5. 变体两人同时 AGREE：节点只完成一次，流程只前进一步；不得重复 spawn 后继任务；最终状态与单线程顺序执行一致。
  6. **不允许的副作用**：重复 REJECT 动作、双份快照、残留 PENDING、流程卡死、500；输家请求若被拒绝应返回 409/422 且不写业务动作（若写“被拒绝”安全审计，不等于业务动作）。
- **反例/边界**：
  - 一人同意后立即驳回（非严格同时）仍应 REJECTED；一人驳回后另一人再同意必须失败（任务已取消）。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`
- **需求待确认项**：TBD-31。

### CONC-01-c 发起人撤回 vs 审批人同意：唯一最终状态，守卫不被绕过

- **需求来源**：PRD §3.5.4“撤回条件：尚无任何任务被处理过”；TECH §4.3 `WITHDRAW`“不存在任何 DONE 的 assignment”；TEST-PLAN §10.2“发起人撤回与审批人同意同时发生”；TBD-31。
- **优先级**：P0
- **验证层**：API（并发请求）
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（首节点审批人）。
  - 表单/流程：自建单审批节点流程；实例 S 已提交，当前 `lisi` PENDING；此前无任何 DONE assignment（抄送已读不算）。
  - 纪录基线：状态 RUNNING、1 个 PENDING、0 DONE。
- **步骤**：
  1. 同步发出 `POST /instances/{S}/withdraw`（发起人）与 `POST /tasks/assignments/{A}/act`（`lisi` AGREE）。
  2. 读取最终状态、任务/指派、时间线、通知、快照。
  3. 重复 20 次；统计两种合法结果各出现次数（不要求固定比例）。
- **期望结果**：
  1. 最终状态只能是以下之一：
     - **WITHDRAWN**：撤回先成功；`lisi` 的 act 返回 409/422；无 DONE assignment；所有任务取消；无审批结果通知。
     - **RUNNING（或按流程继续/APPROVED）**：同意先成功；撤回返回 409/422；实例不得进入 WITHDRAWN；任务按流程继续。
  2. 禁止：WITHDRAWN 且存在 DONE assignment；WITHDRAWN 且仍有 PENDING 任务；RUNNING 但所有任务 CANCELLED 且无 PENDING（卡死）。
  3. 通知一致性：不得同时收到“已撤回”和“审批通过”两条相互矛盾的结果通知。
  4. 时间线只记录实际生效的动作；输家请求不产生业务动作/快照。
  5. **不允许的副作用**：重复撤回、双份取消通知、任务永久 PENDING、500。
- **反例/边界**：
  - 已有任意 DONE assignment 时再撤回：必须 409/422，状态不变（守卫）。
  - 抄送已读不算“已处理”，不影响撤回资格（PRD/TECH 明确）。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`
- **需求待确认项**：TBD-31。

### CONC-01-d 管理员终止 vs 审批人同意：终态唯一，任务清理干净

- **需求来源**：PRD §3.5.4“终止：任意状态（除终态）可用；需填写原因”；TECH §4.3 `TERMINATE`；TEST-PLAN §10.2“管理员终止与审批人同意同时发生”；TBD-31。
- **优先级**：P0
- **验证层**：API（并发请求）
- **前置条件**：
  - 角色与组织：`admin`（终止）、`lisi`（审批人）、`zhangsan`（发起人）。
  - 表单/流程：自建流程，至少两个审批节点；实例 S 当前在第一个审批节点，`lisi` PENDING。
  - 数据：终止原因 `E2E-终止原因`。
- **步骤**：
  1. 同步发出 `POST /instances/{S}/terminate`（带 reason）与 `lisi` 的 `AGREE`。
  2. 读取最终状态、任务/指派、时间线、通知、审计。
  3. 重复 20 次。
  4. 边界：缺 reason 的终止请求与同意并发。
- **期望结果**：
  1. 最终状态只能是 **TERMINATED** 或 **APPROVED**：
     - 若 agree 使流程完成 → APPROVED；终止请求必须失败（终态不允许终止），不得把 APPROVED 改为 TERMINATED。
     - 否则终止成功 → TERMINATED；同意请求失败；若同意在终止前已生效，其动作保留在时间线，但不得继续派发后继任务。
  2. TERMINATED 时：所有 PENDING 任务均取消；无 DONE 之外的新任务；终止原因写入审计/时间线。
  3. APPROVED 时：不存在终止审计/终止通知矛盾。
  4. 边界：缺 reason 的终止 → 422，不改变状态；即使与同意并发，也不得出现“无原因终止成功”。
  5. **不允许的副作用**：同时存在 TERMINATED 与 APPROVED 标记、残留 PENDING、双份终止通知、500、已终止实例仍可 act。
- **反例/边界**：
  - 实例已 APPROVED 后再终止：409/422，状态不变。
  - 实例已 REJECTED/DRAFT 时终止：按 PRD“除终态”可用；DRAFT 是否可终止见 PRD 状态表（DRAFT 可编辑/删除，终止未列），需确认（TBD-31）。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`
- **需求待确认项**：TBD-31。

### CONC-01-e 并行组两端同时汇合 / 或签同时同意：只前进一步，不重复 spawn

- **需求来源**：PRD §3.5.3 并行聚合；TECH §4.3 `plan_after_group`/聚合；TEST-PLAN TASK-04“并行组汇合 all/any 聚合正确；不提前推进、不永久卡住”；§10.2“并行组两端同时汇合”；TBD-31。
- **优先级**：P0
- **验证层**：API（并发请求）
- **前置条件**：
  - 角色与组织：`zhangsan` 发起；`lisi`、`wangwu` 为并行组两分支审批人；`zhaoliu` 为或签组两个成员之一（另建实例）。
  - 表单/流程：
    - 并行组（两个成员分支，各一个审批节点）后接一个审批节点 C。
    - 或签节点（mode=any，成员 `lisi`、`wangwu`）后接节点 C。
  - 实例 S1（并行组）两个分支均 PENDING；S2（或签）两个成员均 PENDING。
- **步骤**：
  1. 对 S1 的两个分支审批任务同步发出两个 `AGREE`。
  2. 读取组状态、后继任务、实例状态、任务数。
  3. 对 S2 的两个或签成员同步发出两个 `AGREE`。
  4. 读取最终状态、被取消的 assignment、后继任务数、通知。
  5. 重复 20 次（S1/S2 各新建）。
- **期望结果**：
  1. S1：组只 JOINED 一次；节点 C 只生成**一套**任务；不出现两套 C 任务、两份额外快照、两次“流程前进”通知。
  2. S2：任一同意使或签通过；另一 assignment 为 CANCELLED(`ANY_SIGN_DONE`)；节点 C 只生成一套任务；被取消人收到“无需处理”知会（PRD §3.5.3）。
  3. 两种场景均不卡死：实例有明确的下一步 PENDING/或进入 APPROVED；不出现“组已 JOINED 但无后继任务”。
  4. 通知：每个事件对每个接收人至多一条；不出现“或签两人都通过”的重复通知。
  5. **不允许的副作用**：重复 spawn、双份 C 任务、组状态 OPEN 但无 PENDING、500。
- **反例/边界**：
  - 或签一人同意后另一人再同意：后者任务已取消 → 409/422，不产生第二次通过。
  - 并行组一端先完成、另一端失败（驳回）：组 FAILED，实例按驳回策略处理，不推进 C（可在 CONC-01-b 的会签变体覆盖）。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`
- **需求待确认项**：TBD-31。

### CONC-01-f 并发字段写入：不同字段合并；同字段后写覆盖且历史快照保留

- **需求来源**：PRD §3.5.3“并发写冲突：同一时刻多任务修改不同字段 → 各自 diff 合并落库；修改同一字段以动作时间序后者覆盖，历史快照均保留”；TEST-PLAN §10.2；TBD-32。
- **优先级**：P0
- **验证层**：API（并发请求）
- **前置条件**：
  - 角色与组织：`zhangsan` 发起；`lisi`、`wangwu` 为并行会签成员，节点对 `amount`、`tax` 两个字段均可编辑。
  - 表单/流程：自建表单含 `amount`、`tax`（number）、`note`（text）；流程含会签节点（mode=all）后结束；实例 S 已提交，两个成员均 PENDING。
  - 数据：初始 `amount=100`、`tax=10`。
- **步骤**：
  1. 变体 A：`lisi` 同时提交 `field_patch={amount:200}` 与 `AGREE`，`wangwu` 同时提交 `field_patch={tax:20}` 与 `AGREE`。
  2. 读取 `amount`、`tax`、diff/快照、时间线、实例状态。
  3. 变体 B（新实例）：两个成员同时提交 `field_patch={amount:300}` 与 `{amount:400}` 并 `AGREE`。
  4. 读取最终 `amount`、两条动作/快照、实例状态。
  5. 重复 10 次/变体。
- **期望结果**：
  1. 变体 A：最终 `amount=200`、`tax=20`（两个不同字段都保留）；不出现一方覆盖另一方的丢失更新；快照包含两次字段变更。
  2. 变体 B：最终 `amount` 为 300 或 400 之一（由服务器串行化顺序决定，TBD-32）；不得出现空值/字符串/中间值；两条动作/快照都保留，可从时间线核对“旧值→新值”。
  3. 会签聚合成一次，实例只前进一步；不重复 spawn。
  4. 两个成员的意见/操作人都被记录；不因同一字段冲突丢意见。
  5. **不允许的副作用**：不同字段互相覆盖、同字段静默丢失一条动作/快照、500、任务卡死。
- **反例/边界**：
  - 使用 `expected_version` 时，后提交者可能 409 `STALE_VERSION`；重试后应成功并满足“后写覆盖”。本用例可分别覆盖“带 version”和“不带 version”两种，TBD-30。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`
- **需求待确认项**：TBD-30、TBD-32。

### CONC-01-g 实例单号（auto_number）并发：同日同前缀不重号、不 500、重提不换号

- **需求来源**：需求方 2026-11-19 确认 R-02（实例单号 = auto_number 字段值）；TECH §3.3“自动编号……number 唯一约束用于并发撞号重试，按标识位+日期每日重置；已有编号在后续暂存/重提中保持不变”；REQ-OPT-FLOW-CONFIG §2/§5；TBD-04。
- **优先级**：P0
- **验证层**：API（并发请求）
- **前置条件**：
  - 角色与组织：`zhangsan`、`wangwu` 均为发起人；`admin`。
  - 表单/流程：自建表单含 `auto_number` 字段 `reqNo`（即实例单号，标识位 `REQ`，4 位流水），流程单审批；发布。
  - 数据：同一测试日内，两名用户各准备一个草稿（或直接并发首次暂存），草稿中不手工填写 `reqNo`。
- **步骤**：
  1. 同步创建/首次暂存 20 个草稿（跨 2 个用户，每个用户 10 个），请求中故意传入伪造 `reqNo="HACK"`。
  2. 读取每个实例的 `reqNo`。
  3. 同步提交其中 10 个（各自独立），检查编号。
  4. 对其中一个实例执行驳回→重提（或撤回后不可重提；用驳回场景），检查编号是否变化。
  5. 在 MySQL/PostgreSQL 上重复（ENV-02）。
- **期望结果**：
  1. 20 个 `reqNo`（实例单号）全部匹配 `REQ<YYYYMMDD><4 位数字>`；彼此唯一；无 `HACK`（客户端传入被忽略）。
  2. 无 500；并发撞号由唯一约束重试解决，所有请求成功或给出可重试的明确错误（不得静默丢失实例）。
  3. 提交不改变实例单号；驳回重提后实例单号保持不变，只有轮次 +1。
  4. 实例单号按“标识位 + 当日流水”每日重置：跨日后的首个编号从当日 `0001` 起；同一天内流水唯一。日期段以哪个时区判定见 TBD-35；无法控制时钟的环境只验证格式、当日唯一与跨日重置的记录。
  5. **不允许的副作用**：重号、跳号导致实例丢失、500、重提换号、客户端伪造值生效。
- **反例/边界**：
  - 同一草稿并发首次暂存两次：仍只生成一个实例单号；不得一个草稿两个实例单号。
  - 删除草稿后当日流水是否回收见 TBD-04；本用例不把“是否回收”纳入通过条件。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`
- **需求待确认项**：TBD-04、TBD-35。

### CONC-01-h 运行中组织变更：已派任务不换人，后续新节点按最新组织派单

- **需求来源**：需求方 2026-11-19 确认 R-01；PRD F6（组织与角色）；TECH §4.3（任务派发与组织解析）；TEST-PLAN §10.2（运行中变更/并发）。
- **优先级**：P0
- **验证层**：API + 浏览器 E2E
- **前置条件**：
  - 角色与组织：`admin`；`zhangsan`（技术部成员）；`lisi`（技术部主管）；`wangwu`（财务部主管）；`zhaoliu`（总公司主管/设计者，非管理员）。组织树按 TEST-DATA，技术部当前主管 = `lisi`。
  - 表单/流程：自建表单与流程，包含两个连续动态派单节点：N1“直属部门主管审批”、N2“部门主管复核”，均按申请人所属部门的主管解析；发布。
  - 实例状态：`zhangsan` 提交实例 S；N1 任务 A1 已派给 `lisi` 且 PENDING；S 尚未进入 N2；`wangwu` 无该实例任务。
- **步骤**：
  1. 确认 A1 的指派人为 `lisi`，`lisi` 待办含 A1，`wangwu` 待办不含 S，S 进度停在 N1。
  2. `admin` 将技术部主管从 `lisi` 改为 `wangwu`（组织变更发生在 A1 已派发之后）。
  3. 立即读取 A1、`lisi`/`wangwu` 的待办、S 的 progress。
  4. `lisi` 对 A1 执行 AGREE；`wangwu` 尝试对 A1 执行 AGREE。
  5. 流程进入 N2 后，读取 N2 任务的指派人与待办归属。
  6. 变体 B（新实例 S2）：在技术部主管为 `wangwu` 时提交；N1 派单后，再用 `admin` 将主管改回 `lisi`，然后让 N1 完成，读取 N2 指派。
  7. 变体 C（换部门）：`admin` 在 S 运行中将 `zhangsan` 从技术部调整到总公司；A1 仍在 `lisi` 待办；让 N1 完成后读取 N2 指派（应为总公司主管 `zhaoliu`）。
- **期望结果**：
  1. 步骤 3：A1 的指派人仍为 `lisi`；`lisi` 待办仍含 A1；`wangwu` 没有 N1 任务；不出现“组织变更导致 A1 被改派/取消”的副作用。
  2. 步骤 4：`lisi` 的 AGREE 成功；`wangwu` 对 A1 的 AGREE 被拒绝（403/404 或 409/422），实例状态不被第二次动作改变。
  3. 步骤 5：N2 任务按**进入 N2 时的最新组织**派给 `wangwu`；只有一条 N2 PENDING 任务；`lisi` 不再收到 N2 任务；不出现两份 N2 任务。
  4. 变体 B：N1 派给 `wangwu`；改回 `lisi` 后，N2 派给 `lisi`；N1 的既有任务不因改回而被追溯改派。
  5. 变体 C：S 的 N1 仍为 `lisi`；进入 N2 时按 `zhangsan` 调整后的部门（总公司）解析，N2 派给总公司主管 `zhaoliu`；不得派给旧部门主管 `lisi`，也不出现两份 N2 任务。
  6. 时间线/通知：N1 记录实际处理人 `lisi`，N2 记录实际处理人 `wangwu`/`zhaoliu`（按变体）；组织变更本身不应伪装成“转办”事件；每个接收人对应任务通知至多一条。
  7. 任何时刻活跃节点恰有一条 PENDING 任务；流程可继续，不卡死。
  8. **不允许的副作用**：已派任务被改派/取消、旧主管与新主管同时可处理、重复任务、流程卡死、500。
- **反例/边界**：
  - 组织变更发生在节点派单**之前**：新节点按变更后的组织派单（与“已派不变、新节点最新”一致）。
  - 组织变更与审批动作严格同时发生：并发输家语义仍按 CONC-01-b/c 的通用不变量判定（TBD-31），但“已派任务不换人”不得被并发绕过。
- **自动化位置**：`backend/tests/test_acceptance_concurrency.py`；`testing/e2e/specs/concurrency.spec.ts`
- **需求待确认项**：无（R-01 已确认）；组织变更与动作严格同时发生时的输家返回码仍见 TBD-31。

---

## 10. 非功能检查清单

> 以下检查项不强行套 Given/When/Then；每项给出**可观察的通过标准**。环境类检查允许查看容器日志/数据库原始值作为证据，但不得把“日志没报错”当作唯一证据。

### 10.1 ENV-01：Docker MySQL/PostgreSQL 全新部署、重启持久化、附件卷

| 检查项 | 方法/步骤 | 通过标准（可观察） | 证据/备注 |
|---|---|---|---|
| ENV-01-1 | 在干净主机/空卷上按部署文档启动 MySQL 8 形态（compose 文件与命令见 TBD-34） | 所有服务进入 healthy/运行状态；`GET /api/v1/healthz` 与 `/readyz` 均 200；`admin` 可登录；迁移已在 head；无手工建表/改库步骤 | 部署命令、容器状态、健康响应、迁移版本 |
| ENV-01-2 | 同上，启动 PostgreSQL 16 形态 | 同 ENV-01-1；日志无方言错误/驱动缺失；中文与 emoji 可写入并可读回 | 同上；PG 版本证据 |
| ENV-01-3 | 首次初始化与种子：记录默认账号、组织、示例流程；分别以 `SEED_DEMO_ACCOUNTS` 关闭/开启重启 | 默认关闭时演示账号不能登录；显式开启后可登录；重复重启不重复创建组织/模板/账号（幂等）；生产默认值符合 TBD-34 | 账号表、组织树、模板数量前后对比 |
| ENV-01-4 | 重启持久化：创建用户/表单/流程/实例/附件后，重启所有容器（不删除卷），再登录 | 上述数据全部存在；实例可打开、时间线完整；附件可下载且字节一致；不出现重复种子/重复实例 | 重启前后 API 结果对比、文件校验和 |
| ENV-01-5 | 附件卷：上传附件；记录文件落点；删除并重建应用容器（保留卷）；再下载 | 文件仍在卷中；DB 元数据与文件一致；容器重建后下载成功；卷权限允许后端写入；删除应用容器不丢失附件 | `docker volume inspect`/挂载点、文件列表、下载校验和 |
| ENV-01-6 | 反向代理/前端入口：通过代理地址登录、深链接刷新、上传/下载附件 | 页面与 API 均可达；深链接不 404；上传/下载不被代理大小限制意外拦截（或与后端上限一致并有明确错误）；无 CORS 错误 | 代理配置、浏览器网络记录 |
| ENV-01-7 | 配置外置与敏感信息：仅改环境变量切换数据库/时区/演示种子；检查镜像与日志 | 无需改代码/重建镜像即可切换；镜像/仓库中无真实密钥；日志不输出密码、JWT、附件内容 | 环境变量清单、镜像内容扫描、日志抽样 |
| ENV-01-8 | 部署 runbook：按文档从零重复一次，记录问题 | 文档步骤可复现；端口/卷/健康检查/回退步骤齐全；本轮发现的问题进入部署 runbook；无“只有某台机器能起”的隐含依赖 | 部署记录、问题清单（TEST-PLAN §10.5） |

### 10.2 ENV-02：空库迁移、上一版本升级、三种数据库核心链路

| 检查项 | 方法/步骤 | 通过标准（可观察） | 证据/备注 |
|---|---|---|---|
| ENV-02-1 | SQLite 空库执行 `alembic upgrade head` → 种子 → 登录 | 迁移成功；`alembic current` 为 head；核心表/约束创建；登录与首页可用；无手工 SQL | 迁移日志、版本号、登录响应 |
| ENV-02-2 | MySQL 8 空库执行同一迁移链 | 同 ENV-02-1；中文/emoji/长文本写入读回一致；唯一约束按预期生效 | 同上；字符集证据 |
| ENV-02-3 | PostgreSQL 16 空库执行同一迁移链 | 同 ENV-02-1/2；无 SQLite 专有语法残留导致的失败 | 同上 |
| ENV-02-4 | 上一发布版本升级：恢复 TBD-33 确定的旧库快照 → `upgrade head` | 升级成功；关键实体数量前后一致（用户/组织/模板/流程/实例/任务/附件）；旧实例可打开、时间线/快照可读；新增列可空、旧数据不受影响；重复执行升级为 no-op | 升级前后计数、抽查实例 render、迁移日志 |
| ENV-02-5 | 三种数据库各跑核心链路：登录 → 发起 → 审批（含驳回/重提）→ 归档 → 检索/导出 | 三种库的可观察结果一致；无方言相关 500；附件上传/下载成功；实例单号（auto_number）唯一；归档 CSV 表头/中文正常；R-03 转义生效 | 三库同一脚本输出对比 |
| ENV-02-6 | 三种数据库各跑检索链路：配置可检索字段 → 提交/审批 → 筛选 → 重建脚本 → 再筛选 | 索引同步/重建结果一致；日期/时间不偏移；重建幂等；分页 total 一致；无 500 | 三库同一夹具结果对比 |
| ENV-02-7 | 迁移链完整性：按文档顺序应用全部迁移（含 M13 检索、M14 转办/委托、M12 共享表格、保留的旧统计表） | 全部迁移按顺序成功；无重复表/索引名冲突；MySQL/PG 索引长度合法（长文本索引不超限）；旧表保留但不再被业务使用（如文档所述） | 迁移列表、schema 对比 |

### 10.3 ENV-03：UTC 存储与 Asia/Shanghai 展示、今日/本周/本月边界

| 检查项 | 方法/步骤 | 通过标准（可观察） | 证据/备注 |
|---|---|---|---|
| ENV-03-1 | UTC 存储：在已知 UTC 时刻创建/提交/审批/完成，读取 API 时间字段 | `created_at/started_at/acted_at/finished_at` 等为 UTC 时刻（与实际 UTC 相差 <1 分钟），不出现 +8 偏移；字段顺序合理（创建≤提交≤完成） | API 响应、与 UTC 时钟对比 |
| ENV-03-2 | 上海展示：浏览器时区 Asia/Shanghai，打开列表/详情/时间线/首页 | 同一时刻显示为 UTC+8；例如 UTC 2026-11-18T16:30Z 显示 2026-11-19 00:30；不出现前一天/后一天错位 | 页面文本、截图 |
| ENV-03-3 | 跨数据库一致性：SQLite/MySQL/PG 各创建一个动作 | 同一输入在三种库上的 API 时间表示一致（同一 UTC 时刻），页面展示一致；无“某个库差 8 小时” | 三库响应对比 |
| ENV-03-4 | 日期字段不位移：`leaveDate=2026-11-19` 的表单值 | 发起页/详情/时间线/CSV 均显示 `2026-11-19`，不因时区变成 18 日或 20 日 | 表单值、CSV |
| ENV-03-5 | “今日”边界：构造上海时间 23:59:59 与次日 00:00:00 的提交/完成事件（时钟注入或预置数据，TBD-35） | `submitted_today`/`finished_this_week` 在 00:00 边界切换；边界前事件计入前一日，边界后计入新一日；不出现 UTC 日界导致的 8 小时错位 | 首页/接口计数对比夹具 |
| ENV-03-6 | “本周”边界：按评审确定的周起始日（默认假设周一，TBD-35）构造周界前后完成事件 | 周起始 00:00 前完成计入上一周，之后计入本周；计数与夹具一致；跨周不重复 | 首页计数、夹具时间 |
| ENV-03-7 | “本月/本年”边界：构造月末/月初、年末/年初完成事件 | `mine_finished_this_month` 只含自然月内 APPROVED；月初 00:00 切换；跨年正确；上月/去年不混入 | 首页计数、归档列表 |
| ENV-03-8 | 导出/通知时间格式：CSV、时间线、通知、页面时间 | 同一事件在各处的时间语义一致；CSV 时间格式符合 TBD-35 约定；无 UTC/本地混用；无 1970/空值 | CSV 抽样、页面抽样 |

### 10.4 PERF-01：1k/10k 实例列表与筛选、100 节点设计器、待办/首页基线

| 检查项 | 方法/步骤 | 通过标准（可观察） | 证据/备注 |
|---|---|---|---|
| PERF-01-1 | 数据集与测量基线：用 API 批量造数；记录硬件、数据库、缓存状态、工具（k6/locust/Playwright Performance API）、采样次数 | 数据集可复现（实例数、字段数、每字段取值分布）；首轮冷缓存与预热后分开记录；至少 3 轮取 P95 | 造数脚本、数据集说明、原始采样 |
| PERF-01-2 | 1,000 实例归档列表（默认分页与按流程筛选） | P95 < 2s（TEST-PLAN §10.3）；无超时/500；分页 total 正确 | 响应时间分布 |
| PERF-01-3 | 10,000 实例归档列表（默认分页与按流程筛选） | P95 < 2s；内存/连接无明显异常增长；结果正确 | 同上 |
| PERF-01-4 | 10,000 实例 + 8 个可检索字段：单条件、三条件组合筛选（MySQL 优先，SQLite 对照） | 验收门槛按 TBD-36 裁定；同时报告单条件/三条件 P95，并与 SEARCH-FILTER-PLAN Phase 4 的 300ms/500ms 目标对比；EXPLAIN 显示命中预期索引（MySQL） | 查询计划、P95 表 |
| PERF-01-5 | 100 节点流程设计器（含条件/并行）打开并操作 | 打开到可交互 < 3s；画布渲染全部节点；选中节点、切换清单/画布、保存成功；发布校验返回且无 500；“可操作”的操作响应上限按 TBD-37 | 浏览器 Performance、录屏/trace |
| PERF-01-6 | 工作台待办 100 条 | 首屏/接口 < 1.5s；分页/计数正确；滚动无明显卡顿 | 响应时间、页面 trace |
| PERF-01-7 | 首页聚合（真实规模数据） | 首屏 `/dashboard/overview` < 1.5s；单请求返回；10 秒轮询请求不叠加/不造成页面卡顿 | 网络记录、响应时间 |

### 10.5 UAT-01：产品负责人独立走完配置、发起审批、驳回重提、检索导出

| 检查项 | 方法/步骤 | 通过标准（可观察） | 证据/备注 |
|---|---|---|---|
| UAT-01-1 | UAT 准备：独立 UAT 环境（重置/种子/账号），提供 UAT 脚本与本文件 P0 期望结果；实现方不现场指导 | 产品负责人拿到可用环境与账号；数据可重置；脚本步骤可执行；签收人明确（TBD-38） | 环境说明、UAT 脚本、签到 |
| UAT-01-2 | 独立配置一条新表单：分区/字段/校验/至少一个补充字段（发起阶段隐藏）+ 发布 | 产品负责人独立完成；发布成功；发起页只显示应显示字段；补充字段发起阶段不可见；无阻断性错误 | 录屏/操作记录、表单版本 |
| UAT-01-3 | 独立配置一条新流程：审批/填写/条件/抄送/字段权限矩阵 + 发布校验 | 流程发布成功；发布校验能拦住至少一个故意配置错误（如无审批人）；无须研发介入 | 流程版本、校验提示 |
| UAT-01-4 | 发起审批：从发起中心找到流程 → 填写 → 保存草稿 → 恢复 → 提交 → 审批人同意 | 草稿可恢复；提交生成正确任务；审批人看到待办；字段权限/时间线符合预期；通知/角标出现 | 页面/API 证据 |
| UAT-01-5 | 驳回重提：审批人驳回并填写意见 → 发起人看到意见/快照 → 修改允许字段 → 重新提交 → 轮次 +1 → 再次审批 | 驳回意见可见；快照可回放；重提轮次 +1；流程从首节点重走；不可编辑字段不可改；再次审批成功 | 时间线、快照、实例 round |
| UAT-01-6 | 检索导出：设计者配置可检索字段 → 管理员归档按业务字段筛选 → 导出 CSV 并用 Excel 打开 | 产品负责人独立完成筛选与导出；CSV 可打开、中文正常、列完整、动态字段有列；筛选结果与列表一致；表单编号（模板编码）与实例单号（auto_number 值）分列且可区分；导出说明含 R-03 转义规则 | CSV、列表截图 |
| UAT-01-7 | 独立性度量：记录完成时间、需要研发协助的次数、被迫绕行的问题 | 全流程无需研发现场指导；无 S1/S2 阻断；如提问，仅限“业务期望确认”，不涉及“怎么操作/哪里点” | UAT 记录 |
| UAT-01-8 | 问题闭环与签收：缺陷分级、歧义回写 TBD/PRD、回归用例登记、最终签收 | 所有阻断问题有结论；S1=0、S2 清零或有明确排期/规避；本文件期望结果由产品负责人确认；签收结论归档 | 缺陷清单、签收记录 |

---

## 11. 用例与需求追踪（本文件范围）

| 需求/场景 | 用例 ID | 主要验证点 |
|---|---|---|
| SEARCH-01 业务字段筛选 | SEARCH-01-a ~ h | 操作符、组合、分页、URL、非法参数、编号语义、mine 权限/草稿 |
| SEARCH-02 索引同步与重建 | SEARCH-02-a ~ f | 提交/草稿、审批更新、事务原子性、重建脚本/幂等、配置生命周期、校验 |
| ARCHIVE-01 归档列表与导出 | ARCHIVE-01-a ~ e | 只含已通过、组合检索、CSV 完整性/中文/动态字段、鉴权、空状态 |
| DASH-01 角色化首页 | DASH-01-a ~ e | 普通用户/管理员/设计者区块、空状态、单请求/轮询、数据隔离 |
| SEC-01 访问控制/IDOR/越权 | SEC-01-a ~ e | 实例/任务/附件/模板/审计/导出、角色越权 |
| SEC-02 数据泄露与内容安全 | SEC-02-a ~ f | hidden 字段、检索侧信道、富文本 XSS、CSV 注入、附件上传安全、抄送人附件权限 |
| CONC-01 并发与幂等 | CONC-01-a ~ h | 重复提交、会签冲突、撤回/终止竞态、并行汇合、字段并发、实例单号并发、运行中组织变更 |
| ENV-01/02/03 | 10.1–10.3 | Docker 部署、迁移升级、三库链路、UTC/上海时区边界 |
| PERF-01 | 10.4 | 1k/10k 列表与筛选、100 节点设计器、待办/首页 |
| UAT-01 | 10.5 | 产品负责人独立 UAT 与签收 |

---

## 12. 待确认项对验收结果的影响（摘要）

- R-01/R-02/R-03/R-04 已确认，CONC-01-h、SEARCH-01-g、ARCHIVE-01-c、SEC-02-d、SEC-02-f 直接按确认口径验收；TBD-03 只影响 `keyword` 是否匹配编号（不影响列表/筛选的两列语义）。
- D-05 已确认：ARCHIVE-01-a/b 只验证 APPROVED 口径；非 APPROVED 查询返回 4xx，不纳入通过条件。
- D-02 已确认：DASH-01-c/e 断言设计者 `admin=null`、无全局概览与管理入口；PHASE3 的相反描述需回写。
- 若 TBD-22 未确认，SEC-01 全部按“403 或 404 均可，但无数据/无副作用”判定；不得据此判失败。
- 若 TBD-24/TBD-25 未确认，SEC-02-c/e 只能验证“无执行/无越权/无路径穿越”，不能验证具体附件白名单或富文本白名单；CSV 转义规则已由 R-03 确认，不在此列。
- 若 TBD-30/TBD-31 未确认，CONC-01 的输家请求只按“409/422/幂等成功”三种可接受结果判定，最终不变量仍必须满足。
- 若 TBD-33/TBD-34 未确认，ENV-02 的“上一版本升级”只能用评审指定的快照执行；ENV-01 的 compose/卷名按实际部署文档记录。
- 若 TBD-36 未确认，PERF-01 同时报告 TEST-PLAN 的 2s 门槛与 SEARCH-FILTER-PLAN 的 300/500ms 目标，不擅自择一作为唯一结论。

---

*（文件结束）*
