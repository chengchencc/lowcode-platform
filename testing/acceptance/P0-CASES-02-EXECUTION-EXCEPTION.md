# P0 验收用例（02）：执行与异常路径

> **状态：DRAFT（待产品/业务评审确认期望结果）**
>
> **生成依据**：FlowForm Spec Pack（`testing/.runtime/spec-pack/`）中的需求、设计、业务文档与 `api/openapi.json` 接口契约。
> 本文件只依据 Spec Pack 设计，未读取 `backend/`、`frontend/`、`testing/e2e/`、`scripts/` 或任何源码/测试代码；未从字段名反推业务规则。
>
> **覆盖场景 ID**：INIT-01、INIT-02、INIT-03、INIT-04、TASK-01、TASK-02、TASK-03、TASK-04、TASK-05、TASK-06、TASK-07、REJECT-01、RETURN-01、WITHDRAW-01、TERMINATE-01、CC-01、EXT-01、NOTIFY-01。
>
> **用例总数**：49 条。
>
> **需求待确认项**：24 条（见第 1 节；原 Q17 已由需求方确认关闭，见 0.2 R4）。期望结果中引用 Q1–Q25 的地方，评审确认后需同步修订用例。
>
> **已确认规则**：4 条（见 0.2 R1–R4），已直接写入期望结果，不再作为待确认项。

---

## 0. 使用说明与夹具约定

### 0.1 断言口径

- **接口错误体**：按 TECH-DESIGN §5，固定为 `{"detail": {"code", "message", "extra"?}}`；用例中的“结构化 4xx”指 HTTP 4xx 且响应体符合该结构。
- **状态值**：使用契约中的 `DRAFT / RUNNING / REJECTED / APPROVED / WITHDRAWN / TERMINATED`；页面文案按 PRD §3.5.1 对应“草稿 / 审批中 / 已驳回 / 已通过 / 已撤回 / 已终止”。
- **实例可观察字段**：`InstanceOut` 的 `status`、`round`、`code`、`abnormal`、`pending_count`、`done_count`、`terminated_reason`；任务列表的 `total`、`TaskRow.status`、`group_id`、`group_member_count`。
- **通知计数**：`GET /api/v1/notifications/unread-count` 与 `GET /api/v1/notifications?unread_only=true` 的 `total`；类型枚举未在 Spec Pack 统一定义（Q20），除 PHASE3 明确命名的 `TASK_TRANSFERRED`、`TASK_DELEGATED` 外，按通知标题/内容/`link` 关联实例断言，不对未定义的类型字符串做硬编码。
- **快照与时间线**：通过 `GET /instances/{id}/timeline`、`GET /instances/{id}/snapshots/{sid}`、`GET /instances/{id}/snapshots/diff?from=&to=` 查询；断言“记录了动作、操作人、节点、时间、意见/原因、字段新旧值”，不引用内部表结构。
- **状态码**：OpenAPI 已明确的（200/201、请求体校验 422、`expected_version` 不符 409）按契约断言；其余非法状态/越权按“结构化 4xx + 无副作用”断言，具体码与文案见 Q10。

### 0.2 已确认规则（需求方 2026-11-19，直接作为期望结果）

- **R1 运行中组织变更**：已派发任务保持原处理人不变；后续进入新节点时，按进入当时最新组织解析派单。覆盖用例：INIT-04-d。
- **R2 编号语义**：表单编号 = 表单模板编码（如 `REIMBURSEMENT`）；实例单号 = 表单内 auto_number 字段值（标识位 + YYYYMMDD + 当日 4 位流水）。列表与筛选必须按该口径区分。覆盖用例：INIT-02-b、TASK-01-a、TASK-01-b。
- **R3 CSV 导出**：以 `=`、`+`、`-`、`@` 开头的单元格，导出时在值前加单引号 `'`，Excel 显示原文本且不执行公式；导出说明中注明该处理。覆盖用例：EXT-01-c。
- **R4 抄送人附件**：跟随字段权限——可见字段的附件可下载；hidden 字段及其附件不可见、不可下载。覆盖用例：CC-01-a、CC-01-b。
- **D-01 部门主管**：部门设置的主管人优先，无则沿部门树向上找最近主管，仍无则转平台管理员并标记异常。覆盖用例：INIT-04-a、INIT-04-b、INIT-04-d。
- **D-02 设计者权限**：设计者只看自己相关，不看全量实例/他人审批数据。覆盖用例：TASK-07 的可见性反例。
- **D-03 并行组退回**：取消整个并行组及后续令牌，实例保持 RUNNING，在目标节点重派；不按组失败/整单驳回处理。覆盖用例：TASK-04-d。
- **D-04 hidden 字段**：运行中严格隐藏（值、附件元数据、导出/打印都不出现）；终态按归档视角。覆盖用例：TASK-05-b。

### 0.3 测试夹具约定（适用于全部用例）

- **环境**：独立测试库与独立附件目录（TEST-PLAN §7.3、TEST-DATA §1/§5）；不连接开发库。
- **账号**：`admin`（平台管理员）、`zhangsan`（技术部普通用户）、`lisi`（技术部主管）、`wangwu`（财务部主管/财务角色）、`zhaoliu`（设计者/总公司主管）。需要额外角色、部门、用户时，由用例内通过 API 工厂创建，命名统一带 `E2E-<runId>-` 前缀。
- **表单/流程**：每个用例自建所需表单与流程，并走真实发布校验；流程发布时锁定表单版本；不直接构造非法定义。
- **实例**：每个用例自行创建实例，前置条件不依赖其他用例的执行顺序；共享同一实例的多角色步骤在自动化中使用串行执行。
- **时间**：委托窗口使用相对当前时间生成的时间戳；跨时区口径见 Q24。

### 0.4 场景覆盖矩阵

| 场景 ID | 用例 ID | 条数 |
|---|---|---|
| INIT-01 发起中心范围 | INIT-01-a、INIT-01-b | 2 |
| INIT-02 发起页 | INIT-02-a、INIT-02-b、INIT-02-c | 3 |
| INIT-03 提交幂等 | INIT-03-a、INIT-03-b | 2 |
| INIT-04 审批人解析 | INIT-04-a、INIT-04-b、INIT-04-c、INIT-04-d | 4 |
| TASK-01 工作台四列表 | TASK-01-a、TASK-01-b | 2 |
| TASK-02 动作守卫 | TASK-02-a、TASK-02-b | 2 |
| TASK-03 会签/或签 | TASK-03-a、TASK-03-b、TASK-03-c、TASK-03-d | 4 |
| TASK-04 并行组汇合 | TASK-04-a、TASK-04-b、TASK-04-c、TASK-04-d | 4 |
| TASK-05 意见/附件/字段修改 | TASK-05-a、TASK-05-b | 2 |
| TASK-06 并发与重复操作 | TASK-06-a、TASK-06-b、TASK-06-c | 3 |
| TASK-07 转办/委托 | TASK-07-a、TASK-07-b、TASK-07-c、TASK-07-d | 4 |
| REJECT-01 驳回与重提 | REJECT-01-a、REJECT-01-b、REJECT-01-c | 3 |
| RETURN-01 退回 | RETURN-01-a、RETURN-01-b | 2 |
| WITHDRAW-01 撤回 | WITHDRAW-01-a、WITHDRAW-01-b、WITHDRAW-01-c | 3 |
| TERMINATE-01 终止 | TERMINATE-01-a、TERMINATE-01-b | 2 |
| CC-01 抄送 | CC-01-a、CC-01-b | 2 |
| EXT-01 运行中追加字段 | EXT-01-a、EXT-01-b、EXT-01-c | 3 |
| NOTIFY-01 消息与角标 | NOTIFY-01-a、NOTIFY-01-b | 2 |
| **合计** |  | **49** |

---

## 1. 需求歧义与待确认清单

| 编号 | 问题 | 涉及用例 | 文档现状/冲突 | 影响与建议 |
|---|---|---|---|---|
| Q1 | 发起范围配置为“指定部门”时，是否包含该部门的子部门？ | INIT-01-a | PRD F2.5/§2 只写“指定部门”；组织树为层级结构；PRD 未定义子部门继承。 | 决定发起授权边界。建议明确“仅本部门”或“含子部门”，并补发布/展示口径。 |
| Q2 | 无发起权限时，直接访问发起页或调用 `available-flows`/`start-options`/创建草稿接口，应返回 403 还是 404？是否隐藏流程存在性？ | INIT-01-b | PRD F2.5 说非授权用户看不到入口；TEST-PLAN INIT-01 只说“直接访问也被拒”，未定义状态码。 | 影响越权反例断言。建议统一为 403（若需隐藏存在性则 404），并给出提示文案。 |
| Q3 | 提交/重提的重复请求，第二次应返回同一实例的 200，还是 409/400？重试是否依赖 `X-Request-Id`？ | INIT-03-a、INIT-03-b | OpenAPI 的 submit/resubmit 未声明 `X-Request-Id`；TECH D7/§3.4 的 request_id 唯一索引落在任务动作 `instance_actions`；SUBMIT 守卫只写了 status ∈ {DRAFT, REJECTED}。 | 用例目前只断言“只产生一个实例/一套任务/一条提交动作”，具体响应语义待定。 |
| Q4 | 实例单号（auto_number）在“首次暂存”即消耗当日流水；删除草稿后序号是否回收？从未暂存直接提交时如何生成？并发撞号重试上限？ | INIT-02-b、INIT-02-c | TECH §3.3 说首次暂存/提交时生成、按“标识位+日期”每日重置；REQ-OPT §5.3 说首次暂存生成并锁定；未定义删除草稿与撞号重试边界。 | 影响编号唯一性与测试数据可重复性。建议明确“不回收、按服务端接收顺序分配”。 |
| Q6 | 审批人未命中且存在多个平台管理员时，任务派给谁（全部管理员/指定主管理员）？`on_empty=block_publish` 的运行时含义？ | INIT-04-b | PRD 说“默认转交平台管理员并标记异常”；AssigneeRule 有 `on_empty` 枚举，但未定义多管理员选择与运行时行为。 | 影响兜底与可追溯性。建议指定单一接收人或明确“全部管理员可见、仅一人处理”的规则。 |
| Q7 | 宽口径来源（角色/部门）剔除发起人后为空时，是否按“未命中”转管理员异常？ | INIT-04-c | TECH §3.3 说角色/部门等宽口径来源会剔除发起人；PRD 说未命中任何审批人转管理员并标记异常；未明确剔除后为空的处理。 | 影响自审边界。建议明确：剔除后为空按未命中处理，不静默通过、不回退为自审。 |
| Q8 | “发起人指定审批人”（`initiator_select`）的候选范围如何限定？未选人、选择范围外用户、选择停用用户时如何拦截？ | INIT-04-a | PRD F3.5 只说提交前先选人；`SubmitRequest.assignee_picks` 与 `AssigneeSource.scope_role_ids/scope_dept_ids` 存在，但 PRD 未描述候选范围与校验。 | 影响提交守卫与派单。建议明确候选范围来源与未选人时的错误提示。 |
| Q9 | “会签组待办合并展示”的合并单位是什么：同一用户在同一并行组的多个待办合并为一行，还是同一会签任务的多条指派合并提示？“同组 N 人”提示文案？ | TASK-01-b | PRD F4.1 说“会签组待办合并展示、分别操作”；TECH TaskRow 提供 `group_id`/`group_member_count`；未定义 UI 合并口径。 | 影响工作台可观察结果。建议确认“一行对应一个 assignment，组信息以标签提示”，或明确真正的合并行。 |
| Q10 | 非法状态/越权动作的统一错误码与提示文案：403、404、409、422 的使用边界。 | TASK-02-b、TASK-06-b、REJECT-01-b、RETURN-01-b、WITHDRAW-01-b、TERMINATE-01-b | TECH §5 固定错误体结构；OpenAPI 只列 200/422；TEST-PLAN PERM-03 允许越权 ID 返回 403/404；状态冲突未统一。 | 影响所有反向用例的可断言性。建议在接口契约中补充每个守卫的错误码表。 |
| Q11 | 被取消任务（或签其余、并行组其余、驳回/终止/撤回导致取消）是否生成站内通知？通知类型/文案？是否出现在“已办”？ | TASK-03-b、TASK-03-c、TASK-04-b、NOTIFY-01-b | PRD §3.5.3 说被取消人收到“无需处理”知会；F4.5 说知会并在待办移除；PHASE3 只定义转办后在已办显示“已转办”，未定义取消的已办归属。 | 影响通知与列表断言。建议明确取消知会的形式与已办展示。 |
| Q14 | 退回后，下游节点已填写的数据是否对目标和后续节点可见？被取消节点的旧任务在“已办”和时间线中如何呈现？ | RETURN-01-a | PRD 说“字段数据保留（不回滚）”；未定义已取消任务在已办的展示与下游字段的可见性。 | 影响“数据不回滚”的可验证口径。建议明确保留全部值与历史动作，仅重派目标节点。 |
| Q15 | 撤回的“尚无任何任务被处理过”边界：转办、委托派发、或签取消是否算“处理过”？DRAFT 是走 withdraw 还是删除草稿？ | WITHDRAW-01-a、WITHDRAW-01-b、WITHDRAW-01-c | PRD 状态图 DRAFT→WITHDRAWN 标注“发起人删除草稿”；TECH WITHDRAW 守卫只排除 DONE 的 assignment，并明确“抄送已读不算”；未定义转办/委托/取消。 | 影响撤回守卫。建议明确“只有 DONE 的处理动作算处理过”，并区分 DRAFT 的删除与撤回入口。 |
| Q16 | 终止是否允许 DRAFT（PRD 状态图只画 RUNNING/REJECTED→TERMINATED，正文说“任意状态（除终态）”）？终止通知的接收范围？ | TERMINATE-01-a、TERMINATE-01-b | PRD §3.5.4 表格说“任意状态（除终态）可用”；状态图未画 DRAFT→TERMINATED。 | 影响终止守卫与通知断言。建议明确 DRAFT 是否由管理员终止或仅能删除。 |
| Q18 | 追加字段的可见起点（当前节点是否立即可见）、通知接收人、允许的控件类型清单（是否含人员/部门控件）？ | EXT-01-a、EXT-01-b | PRD §3.4 机制 C 说“对当前及后续节点可见（默认只读，仅目标节点可编辑）”，基础控件为文本/数字/日期/下拉/附件；TECH L5 以 `visible_from_node_id` 判定；TECH M5 提到通知，但未写接收人。 | 影响追加字段的可见与通知断言。建议确认控件白名单与通知对象。 |
| Q19 | 追加字段“停用/隐藏”后，已填值在详情、快照、归档、导出中如何呈现？ | EXT-01-b | PRD F5.3 只说可停用/隐藏、不可物理删除；未定义停用后的数据展示。 | 影响归档完整性与审计。建议明确“停用仅停止编辑/展示，历史值与快照保留”。 |
| Q20 | 站内通知的类型枚举、标题文案，以及“处理结果”通知的触发粒度：每次审批动作都通知发起人，还是仅最终通过/驳回/终止？ | NOTIFY-01-a、NOTIFY-01-b | PRD F7.1 列举通知事件；OpenAPI 的 `type` 是自由字符串；TECH/PHASE3 只明确 `TASK_TRANSFERRED`、`TASK_DELEGATED`。 | 影响通知数量断言。建议发布通知类型字典与触发矩阵。 |
| Q21 | 填写节点是否支持“意见/附件必填”配置？ | TASK-05-a、TASK-02-b | PRD F4.3 的“意见、附件必填可配置”位于处理操作区泛指；OpenAPI 只有审批节点有 `opinion_required`/`attachment_required`，填写节点没有。 | 影响填写节点用例的校验断言。建议明确填写节点是否支持，或从 PRD 收窄描述。 |
| Q22 | `reject_policy=reject_forbidden` 时，审批人界面如何呈现驳回？点击驳回是隐藏、禁用还是返回错误？ | REJECT-01-b | PRD §3.5.4 只写“也可配置驳回至发起人且不允许再提（废弃）”；未定义可见行为与接口守卫。 | 影响驳回动作可用性与验收。建议明确“按钮不可用 + 服务端拒绝”。 |
| Q23 | 隐藏/只读字段被客户端伪造写入时，是整单拒绝还是静默过滤？ | INIT-02-c、TASK-05-b、REJECT-01-b | PRD F3.2 说后端二次校验；PERM-02 说“伪造提交值被过滤”；PHASE2 M9 说“隐藏字段的非法修改不落库”。未统一“过滤还是整单拒绝”。 | 影响反向用例断言。建议明确：非法字段值一律不落库；是否返回 4xx 按字段性质区分。 |
| Q24 | 委托窗口的时区口径（前端本地时间 vs 服务端 UTC/应用时区）与重叠判定是否含端点？委托取消/到期后，已派出的待办是否保留在被委托人处？ | TASK-07-c、TASK-07-d | PHASE3 §4.2 说按 `start_at <= 当前时间 < end_at` 判断、到期自动失效、已派出不回退；未定义时区与取消场景。 | 影响委托边界测试与用户预期。建议明确统一使用应用时区并在界面提示。 |
| Q25 | 草稿自动暂存的触发频率、失败重试、多标签页并发写策略？ | INIT-02-b | PRD F3.3 只要求自动暂存与恢复；未定义频率、冲突与失败提示。 | 影响 E2E 等待策略与并发草稿测试。建议明确“编辑停止后 N 秒暂存，后写覆盖并提示”。 |

> 原 Q17 已由 R4 关闭；Q5 由 D-01 关闭；Q12/Q13 由 D-03 关闭。Q2/Q6/Q7/Q10/Q15/Q16/Q20–Q25 按 `P0-DECISIONS.md` §4 默认执行，表中保留为文档回写备忘。

---

## 2. 用例

### 2.1 发起与提交

#### INIT-01 发起中心范围

### INIT-01-a 发起中心按“全员/角色/部门”范围过滤入口

- **需求来源**：PRD F2.5、F3.1；TEST-PLAN §6.5 INIT-01；OpenAPI `GET /api/v1/instances/available-flows`、`GET /api/v1/instances/start-options/{flow_template_id}`
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（技术部，普通用户，无“财务”角色）；`wangwu`（财务部，角色“财务”）；运行内创建 `E2E-<runId>-tech-fin`（技术部，仅“财务”角色），用于验证角色范围跨部门生效。
  - 表单/流程版本与状态：API 工厂创建并发布 3 条流程，均绑定同一已发布表单：F_all（发起范围 all）、F_role（发起范围 role=“财务”）、F_dept（发起范围 dept=财务部）；全部通过发布校验。
  - 实例状态与数据：无实例、无草稿。
- **步骤**：
  1. `zhangsan` 打开发起中心，并调用 `GET /instances/available-flows`。
  2. `wangwu` 打开发起中心。
  3. `E2E-<runId>-tech-fin` 调用 `GET /instances/available-flows`。
  4. 对可见流程分别调用 `GET /instances/start-options/{flow_template_id}`。
- **期望结果**：
  1. 页面/接口可观察结果：`zhangsan` 只看到 F_all 卡片；`wangwu` 看到 F_all、F_role、F_dept；技术部的“财务”角色用户能看到 F_role（角色范围与部门无关），但看不到 F_dept；同一流程即使同时命中角色与部门也只出现一张卡片。
  2. 数据副作用：`start-options` 返回的 `flow_version_id`、`form_version_id` 与已发布版本一致；不创建实例、草稿或任务。
  3. 通知/审计副作用：无通知；无实例相关审计记录。
- **反例/边界**：
  - 部门范围是否包含子部门见 Q1；本用例不把子部门用户作为通过条件。
- **自动化位置**：`testing/e2e/specs/initiate.spec.ts`；API 断言建议置于 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q1

### INIT-01-b 反向：无发起权限时直接访问发起页/接口被拒且无副作用

- **需求来源**：PRD F2.5、PRD §2；TEST-PLAN §6.5 INIT-01；OpenAPI `GET /instances/start-options/{flow_template_id}`、`POST /instances/drafts`
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（技术部普通用户，无“财务”角色、不在财务部）；`wangwu`（财务部）。
  - 表单/流程版本与状态：发布流程 F_role（发起范围 role=“财务”）与 F_dept（发起范围 dept=财务部），均绑定已发布表单。
  - 实例状态与数据：无实例、无草稿。
- **步骤**：
  1. `zhangsan` 直接访问 `/start/{F_role.flow_template_id}` 页面，并调用 F_role 的 `start-options`。
  2. `zhangsan` 调用 `POST /instances/drafts`，`flow_template_id` 指向 F_role。
  3. `zhangsan` 对 F_dept 重复步骤 1–2。
  4. 查询 `zhangsan` 的草稿箱与“我发起的”列表。
- **期望结果**：
  1. 页面/接口可观察结果：发起页不渲染可提交的表单（或跳转到无权限提示），`start-options` 返回结构化 4xx（建议 403；若产品要求隐藏存在性则 404，见 Q2）；创建草稿同样被拒。
  2. 数据副作用：`zhangsan` 的草稿箱为空，“我发起的”列表 `total=0`；没有新实例、任务、快照或通知。
  3. 通知/审计副作用：无通知；无实例审计记录。
- **反例/边界**：
  - 若接口返回 200 但前端隐藏入口，不视为通过：直接调用必须被服务端拒绝。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）；页面部分可补 `testing/e2e/specs/initiate.spec.ts`
- **需求待确认项**：Q2

#### INIT-02 发起页

### INIT-02-a 发起页渲染：自动填充、默认值、隐藏字段、只读字段与标题字段

- **需求来源**：PRD F3.2、F3.3；TECH §3.3（`auto_fill`、`default_source`、自动编号、公式）；PHASE2 §2.6（标题字段）；TEST-PLAN §6.5 INIT-02
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（技术部）。
  - 表单/流程版本与状态：发布表单，包含：标题字段 `title`（顶层文本，设为 `title_field`）、申请人 `applicant`（人员，`auto_fill=initiator`）、申请部门 `dept`（部门，`auto_fill=initiator_dept`）、申请时间 `start_time`（日期时间，`auto_fill=start_time`）、需求负责人 `owner`（人员，`default_source=initiator`）、事由 `reason`（文本，必填）、天数 `days`（公式=日期差）、补充说明 `secret_note`（文本，`visible_at_start=false`，位于补充区）、附件 `files`（附件）；流程为 start → 审批节点 → end，审批节点对 `secret_note` 可编辑；流程发布时锁定该表单版本。
  - 实例状态与数据：无实例、无草稿。
- **步骤**：
  1. `zhangsan` 打开 `/start/{flow_template_id}`。
  2. 观察各字段的初始值与可编辑状态。
  3. 修改 `owner`，填写 `reason` 与起止日期，观察 `days`。
  4. 调用 `GET /instances/start-options/{flow_template_id}`，比对页面。
- **期望结果**：
  1. 页面/接口可观察结果：`applicant` 自动为“张三”、`dept` 自动为“技术部”、`start_time` 为服务端发起时间，三者只读（无编辑框）；`owner` 预填“张三”但可修改；`secret_note` 在发起页与 `start-options` 的字段权限中均为隐藏，不渲染输入框、不出现标签；`days` 按公式计算且只读；`title` 是该表单的标题来源，发起页不再额外出现一个“标题”输入框；流程模板未配置 `title_field` 时，实例标题回退为流程模板名（另建一条流程验证）。
  2. 数据副作用：无实例、无任务；`start-options` 不返回 `secret_note` 的可编辑权限。
  3. 通知/审计副作用：无通知。
- **反例/边界**：
  - 隐藏字段不得通过页面源码或接口响应泄露（仅断言“不渲染/不在权限中”，值泄露由 INIT-02-c 覆盖）。
- **自动化位置**：`testing/e2e/specs/initiate.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：无（标题回退规则来自 PHASE2 §2.6）

### INIT-02-b 草稿自动暂存、恢复与“草稿不生成任务”

- **需求来源**：PRD F3.3；TECH §3.3（自动编号）；REQ-OPT §5.3（首次暂存生成编号）；TEST-PLAN §6.5 INIT-02
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（技术部）；审批人 `lisi`。
  - 表单/流程版本与状态：发布表单，表单模板编码为 `E2E-<runId>-DRAFT`，含必填 `reason`、auto_number 字段 `req_no`（实例单号：标识位 `E2E` + YYYYMMDD + 当日 4 位流水）、附件字段；流程为 start → 审批节点（lisi）→ end，已发布并锁定表单版本。
  - 实例状态与数据：无实例、无草稿。
- **步骤**：
  1. `zhangsan` 打开发起页，填写 `reason` 并保存/等待自动暂存（Q25）。
  2. 刷新页面或重新进入草稿箱，打开该草稿。
  3. 修改 `reason`，再次暂存；提交草稿。
  4. 查询 `zhangsan` 的草稿箱、`lisi` 的待办、实例详情、时间线与通知。
- **期望结果**：
  1. 页面/接口可观察结果：草稿在草稿箱中可见，标题来自标题字段或流程名回退规则；重新打开后已填字段恢复，`req_no` 已生成且再次暂存不变；草稿状态为 `DRAFT`；列表中该单的“实例单号”显示 `req_no` 值，“表单编号”显示 `E2E-<runId>-DRAFT`，两者不混用（R2）。
  2. 数据副作用：草稿阶段 `lisi` 待办 `total=0`，无任务、无提交动作、无快照；提交后实例转为 `RUNNING`、`round=1`，恰好生成 1 个首个节点任务，草稿从草稿箱移除，`req_no` 保持不变。
  3. 通知/审计副作用：草稿阶段无通知；提交后 `lisi` 收到 1 条新待办通知。
- **反例/边界**：
  - 自动暂存失败/多标签并发策略见 Q25；本用例不把“固定 N 秒”作为业务断言，自动化可轮询草稿箱直至出现或超时判失败。
  - 编号在删除草稿后的回收规则见 Q4；本用例不断言序号复用。
- **自动化位置**：`testing/e2e/specs/initiate.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q4、Q25

### INIT-02-c 反向：绕过前端提交时，必填、隐藏字段、自动填充与公式由服务端兜底

- **需求来源**：PRD F3.2（前端校验+后端二次校验）、F3.3；TECH §3.3；PERM-02（伪造提交值被过滤）；PHASE2 §3.4（隐藏字段非法修改不落库）
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（技术部）。
  - 表单/流程版本与状态：发布表单，含必填 `reason`、`amount`（数字，值规则 1–10000）、`days`（公式）、`secret_note`（`visible_at_start=false`）、`applicant`（`auto_fill=initiator`）、`start_time`（`auto_fill=start_time`）；流程已发布。
  - 实例状态与数据：由 `zhangsan` 通过 API 创建 1 个 `DRAFT`，已有 `reason="R"`。
- **步骤**：
  1. 直接调用 `POST /instances/{id}/submit`，`data` 中缺少 `reason`。
  2. 修正 `reason`，但传入 `secret_note="伪造补充"`、`applicant=<他人 id>`、`start_time="2000-01-01T00:00:00"`、`amount=99999`、`days=999`。
  3. 查询实例详情、数据快照、时间线与任务。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1 返回结构化 4xx（业务校验错误，建议 422，见 Q10/Q23），实例仍为 `DRAFT`；步骤 2 若被接受，则接口成功但非法值不得生效，若被拒绝则保持 `DRAFT`。
  2. 数据副作用：无论步骤 2 成功或失败，实例数据中不得出现 `secret_note` 的值；`applicant` 必须为 `zhangsan`，`start_time` 必须为服务端生成的发起时间；`days` 必须由服务端按公式重算；`amount=99999` 必须被值规则拦截（整单拒绝或该字段不落库，见 Q23）；不产生重复任务。
  3. 通知/审计副作用：失败请求不产生通知、提交动作或快照；成功请求只产生 1 条提交动作与 1 份提交快照。
- **反例/边界**：
  - 隐藏/只读字段注入的“整单拒绝 vs 静默过滤”见 Q23；用例的硬性断言是“非法值不落库、不泄露”。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q4、Q10、Q23

#### INIT-03 提交幂等

### INIT-03-a 同一草稿连点/网络重试提交：只产生一个实例与一套任务

- **需求来源**：TECH §3.4（HTTP 重放、派发幂等）、D7；TEST-PLAN §6.5 INIT-03；PRD §7（一致性：审批动作幂等、并发提交不产生重复任务）
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）；`lisi`（首个审批节点处理人）；`wangwu`（第二节点处理人）。
  - 表单/流程版本与状态：发布流程 start → 审批(lisi) → 审批(wangwu) → end，绑定已发布表单。
  - 实例状态与数据：`zhangsan` 的 `DRAFT` 实例 1 个，数据完整可提交。
- **步骤**：
  1. 对同一草稿并发发出 2 个完全相同的 `POST /instances/{id}/submit` 请求（模拟双击/网络重试）。
  2. 查询 `zhangsan` 的“我发起的”、实例详情、`lisi` 的待办、时间线与快照。
  3. 再次以相同 `X-Request-Id` 重放提交请求（若接口支持，见 Q3）。
- **期望结果**：
  1. 页面/接口可观察结果：`zhangsan` 的“我发起的”中该单只有 1 条，`code` 不变；实例状态 `RUNNING`、`round=1`；`lisi` 待办恰好 1 条。
  2. 数据副作用：只有 1 条提交动作、1 份提交快照、1 套首个节点任务；第二次/重放请求不得新增任务、改变轮次或产生第二个实例；无 5xx。
  3. 通知/审计副作用：`lisi` 只收到 1 条新待办通知；审计中只有 1 条提交记录。
- **反例/边界**：
  - 第二次请求返回“同一成功结果”还是 409/400 见 Q3；本用例不把具体码作为通过条件，但要求响应可解释且无副作用。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q3

### INIT-03-b 两个会话并发提交同一草稿：唯一生效，另一请求不产生副作用

- **需求来源**：TECH §3.4（实例级互斥、乐观锁）、PRD §7；TEST-PLAN §6.5 INIT-03
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan` 拥有两个独立登录会话（两个 token）；`lisi` 为首个审批人。
  - 表单/流程版本与状态：发布流程 start → 审批(lisi) → end。
  - 实例状态与数据：`zhangsan` 的 `DRAFT` 实例 1 个，数据完整可提交。
- **步骤**：
  1. 两个会话同时提交同一草稿（不使用共享 `X-Request-Id`）。
  2. 查询实例、任务、时间线、通知与快照。
- **期望结果**：
  1. 页面/接口可观察结果：两个响应要么都指向同一实例的成功结果，要么一个成功、另一个为结构化 4xx（见 Q3）；不得出现 5xx。
  2. 数据副作用：实例只进入 `RUNNING` 一次，`round=1`；只有一套首个节点任务；只有 1 条提交动作与 1 份提交快照；没有“状态已变更但任务为空”的中间态。
  3. 通知/审计副作用：`lisi` 只收到 1 条新待办通知；无重复审计记录。
- **反例/边界**：
  - 若两个请求都成功但都返回同一实例，也视为通过；关键是数据唯一。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q3

#### INIT-04 审批人解析

### INIT-04-a 多来源审批人解析正确并快照到任务

- **需求来源**：PRD §3.3.2（指定人员/角色/部门主管/表单人员/发起人指定/组合与快照）、F3.5；TECH §3.3；TEST-PLAN §6.5 INIT-04
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（技术部，发起人）；`lisi`（技术部主管）；`wangwu`（财务部主管，角色“财务”）；`zhaoliu`（总公司主管）；运行内创建 `E2E-<runId>-u1`、`E2E-<runId>-u2`（均为启用普通用户）。
  - 表单/流程版本与状态：发布表单，含人员字段 `owner`（发起人填 `admin`）与部门字段 `target_dept`；发布流程 start → 并行组（mode=all），组内 6 个审批成员：
    1. 部门主管（发起人所在部门，期望 `lisi`）
    2. 角色“财务”（期望 `wangwu`）
    3. 部门主管（固定部门=总公司，期望 `zhaoliu`）
    4. 表单人员字段 `owner`（期望 `admin`）
    5. 指定人员 `E2E-<runId>-u1`
    6. 发起人指定（`initiator_select`，提交时选择 `E2E-<runId>-u2`）
  - 实例状态与数据：`zhangsan` 的 `DRAFT`，`owner=admin`，已选择 `E2E-<runId>-u2` 作为发起人指定审批人。
- **步骤**：
  1. `zhangsan` 提交。
  2. 查询实例进度与 6 个任务的处理人。
  3. 分别以各处理人身份查询待办。
- **期望结果**：
  1. 页面/接口可观察结果：并行组内 6 个审批任务同时生成，处理人分别为 `lisi`、`wangwu`、`zhaoliu`、`admin`、`E2E-<runId>-u1`、`E2E-<runId>-u2`；实例状态 `RUNNING`，`abnormal=false`；进度条并列展示 6 个成员。
  2. 数据副作用：每个任务的处理人按进入节点时的解析结果快照保存；任务数为 6；不产生未解析来源的空任务；不重复派发给同一人。
  3. 通知/审计副作用：6 个处理人各收到 1 条新待办通知；时间线显示提交与并行组成员派发。
- **反例/边界**：
  - “部门主管”按 D-01 解析：本部门主管人优先，无则沿部门树向上找最近主管；本用例直接按该口径断言。
  - `initiator_select` 候选范围见 Q8。
- **自动化位置**：`testing/e2e/specs/initiate.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q5、Q8

### INIT-04-b 审批人未命中时转平台管理员并标记异常，不静默通过

- **需求来源**：PRD §3.3.2（未命中转交平台管理员并标记异常）、F2.7；TECH §3.3；TEST-PLAN §6.5 INIT-04；DEMO §4（异常提示）
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：运行内创建 `E2E-<runId>-init`（普通用户）与 `E2E-<runId>-無主管部`（无主管）；`init` 属于该部门；`admin`（平台管理员）存在且启用。
  - 表单/流程版本与状态：发布流程 start → 审批节点（来源=发起人所在部门的部门主管）→ end，已发布。
  - 实例状态与数据：`E2E-<runId>-init` 的 `DRAFT`，数据完整。
- **步骤**：
  1. `E2E-<runId>-init` 提交。
  2. 查询实例详情、`admin` 待办、`init` 的“我发起的”与通知。
- **期望结果**：
  1. 页面/接口可观察结果：实例状态 `RUNNING`、`abnormal=true`；详情页显示“异常”标记；审批任务派给平台管理员 `admin`；`init` 侧不显示可处理按钮，也不显示“已通过”。
  2. 数据副作用：任务数为 1，处理人 `admin`；没有任何自动同意/自动通过的动作；实例不会因未命中而进入 `APPROVED`。
  3. 通知/审计副作用：`admin` 收到 1 条待办/异常通知；无静默通过审计。
- **反例/边界**：
  - 多个管理员时派给谁见 Q6；`on_empty=block_publish` 的运行时行为见 Q6，本用例使用默认 `to_admin`。
- **自动化位置**：`testing/e2e/specs/initiate.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q5、Q6

### INIT-04-c 自审边界：表单人员显式指向发起人允许自审，宽口径来源剔除发起人

- **需求来源**：TECH §3.3（自审例外与宽口径剔除）；PRD §3.3.2；TEST-PLAN §6.5 INIT-04
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：运行内创建 `E2E-<runId>-self`（启用普通用户）；`admin`；创建角色 `E2E-<runId>-role-self`，唯一成员为 `E2E-<runId>-self`。
  - 表单/流程版本与状态：
    - 流程 A：start → 审批节点（来源=表单人员字段 `owner`）→ end；已发布。
    - 流程 B：start → 审批节点（来源=角色 `E2E-<runId>-role-self`）→ end；已发布。
    - 表单含人员字段 `owner`。
  - 实例状态与数据：两份 `DRAFT`，发起人均为 `E2E-<runId>-self`；流程 A 的 `owner` 选为发起人本人。
- **步骤**：
  1. 提交流程 A 的实例，查询任务处理人。
  2. 提交流程 B 的实例，查询任务处理人与实例 `abnormal`。
- **期望结果**：
  1. 页面/接口可观察结果：流程 A 的任务派给发起人本人，实例 `abnormal=false`，发起人可在自己的待办中处理（自审允许）；流程 B 的任务不派给发起人，按“未命中”转平台管理员 `admin` 且 `abnormal=true`（若产品确认其他兜底，见 Q7）。
  2. 数据副作用：两个实例均为 `RUNNING`，均不被自动通过；流程 B 的任务数为 1（管理员），不是 0。
  3. 通知/审计副作用：流程 A 发起人收到自己的待办通知；流程 B 管理员收到兜底任务通知。
- **反例/边界**：
  - 角色/部门宽口径来源剔除发起人后为空时的处理见 Q7；本用例按 TECH 的“剔除 + 未命中兜底”断言。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q7

### INIT-04-d 运行中组织变更：已派任务不变，后续节点按最新组织解析

- **需求来源**：需求方确认规则 R1（2026-11-19）；PRD §3.3.2（进入节点时解析并快照审批人）；TECH §3.3
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：运行内创建部门 `E2E-<runId>-dept`，初始主管为 `lisi`；`wangwu`、`zhaoliu` 为启用用户；`admin` 可修改组织。
  - 表单/流程版本与状态：发布流程 start → `N1`（部门主管，固定部门=`E2E-<runId>-dept`）→ `N2`（部门主管，固定部门=`E2E-<runId>-dept`）→ end；已发布。
  - 实例状态与数据：`zhangsan` 已提交，实例 `RUNNING`，停在 `N1`，处理人为 `lisi`。
- **步骤**：
  1. `admin` 将 `E2E-<runId>-dept` 的主管由 `lisi` 改为 `wangwu`。
  2. 查询 `N1` 任务的处理人，并由 `lisi` 同意。
  3. 查询 `N2` 任务的处理人。
  4. `admin` 再将主管改为 `zhaoliu`；查询 `N2` 任务。
- **期望结果**：
  1. 页面/接口可观察结果：组织变更后 `N1` 仍为 `lisi`，不被取消或改派，`lisi` 可正常同意；`N2` 在进入时按最新组织解析，派给 `wangwu`，`lisi`/`zhaoliu` 无该待办；步骤 4 的组织变更不影响已派发的 `N2`，仍为 `wangwu`。
  2. 数据副作用：`N1`、`N2` 各只有 1 条任务；处理人快照分别为 `lisi`、`wangwu`；无重复任务、无 `abnormal=true`；实例状态正常推进。
  3. 通知/审计副作用：组织变更不产生实例内任务通知；`lisi` 同意后 `wangwu` 收到 1 条 `N2` 新待办通知；时间线按顺序记录两次审批。
- **反例/边界**：
  - 若组织变更发生在 `N1` 派发前，则应按变更后组织派发；本用例固定“先派发、后变更”的顺序。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：无（R1 已确认）

### 2.2 审批工作台与任务

#### TASK-01 工作台四列表

### TASK-01-a 待办/已办/我发起/抄送四列表口径与计数正确

- **需求来源**：PRD F4.1；TECH §4.2、§5.3；TEST-PLAN §6.6 TASK-01；OpenAPI `GET /tasks/todo|done|mine|cc|summary`
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`、`zhaoliu`、`admin`。
  - 表单/流程版本与状态：发布流程 start → 审批 `N1`(lisi) → 审批 `N2`(wangwu) → 抄送(zhaoliu) → end，绑定已发布表单；表单模板编码为 `E2E-<runId>-LEAVE`，表单含 auto_number 字段，各实例的实例单号为 `E2E` + YYYYMMDD + 4 位流水（R2）。
  - 实例状态与数据：
    - I1：`RUNNING`，停在 N1，lisi 待办；发起人 zhangsan。
    - I2：`RUNNING`，已过 N1、停在 N2，wangwu 待办；lisi 已办；发起人 zhangsan。
    - I3：`APPROVED`，lisi、wangwu 已办；抄送节点已派发给 zhaoliu（未读）；发起人 zhangsan。
- **步骤**：
  1. `lisi` 打开工作台，分别查看待办/已办/我发起的/抄送给我，并调用四个列表接口与 `summary`。
  2. `wangwu` 同样操作。
  3. `zhaoliu` 查看抄送列表。
  4. `zhangsan` 查看“我发起的”与 `summary`。
- **期望结果**：
  1. 页面/接口可观察结果：`lisi` 待办只含 I1，已办含 I2，我发起为空，抄送为空；`wangwu` 待办只含 I2，已办含 I3；`zhaoliu` 抄送含 I3（`is_read=false`），待办/已办不含 I3；`zhangsan` 我发起含 I1、I2（审批中）与 I3（已通过）；列表列头使用“实例单号”与“表单编号”两个口径，“实例单号”显示 auto_number 值，“表单编号”显示表单模板编码 `E2E-<runId>-LEAVE`（R2）。
  2. 数据副作用：各列表 `total` 与页面计数一致；`summary.todo`、`cc_unread`、`mine_running` 与对应列表一致；不同用户之间不串数据；编号列口径不混用。
  3. 通知/审计副作用：不影响实例状态；无额外动作记录。
- **反例/边界**：
  - 抄送任务不得出现在待办/已办；发起人不得因是发起人而出现在待办。
- **自动化位置**：`testing/e2e/specs/approve.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q9（组提示口径）

### TASK-01-b 待办筛选、分页与会签组提示

- **需求来源**：PRD F4.1（会签组待办合并展示、分别操作）；TEST-PLAN §6.6 TASK-01；OpenAPI `GET /tasks/todo` 的 `keyword`、`flow_template_id`、`page`、`size`
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`lisi`、`wangwu`、`zhaoliu`、`zhangsan`；运行内创建 `E2E-<runId>-outsider`。
  - 表单/流程版本与状态：发布两条流程 F1、F2，均绑定已发布表单；表单模板编码分别为 `E2E-<runId>-F1`、`E2E-<runId>-F2`，表单均含 auto_number 字段，实例单号为 `E2E` + YYYYMMDD + 4 位流水；F1 含一个并行组（mode=all），组内两个审批成员的处理人均配置为 `lisi`（同一用户在不同成员节点各有一条待办）；F2 为普通单审批流程（处理人 `zhaoliu`）。
  - 实例状态与数据：F1 实例 1 个（`RUNNING`，lisi 两条待办，同组）；F2 实例 1 个（`RUNNING`，zhaoliu 待办）；另创建若干不同标题的 F2 实例用于分页。
- **步骤**：
  1. `lisi` 调用 `/tasks/todo?size=1&page=1`、`page=2`，再按 `flow_template_id=F1` 与 `keyword=<标题片段>` 过滤。
  2. 打开工作台待办页，观察两条同组待办的展示。
  3. 在筛选区分别按 F1 的实例单号、表单编号 `E2E-<runId>-F1`、F2 的表单编号 `E2E-<runId>-F2` 过滤。
  4. `E2E-<runId>-outsider` 调用`/tasks/todo`。
- **期望结果**：
  1. 页面/接口可观察结果：分页 `total/page/size` 正确，翻页不重复不遗漏；`flow_template_id` 只返回 F1 的任务；按实例单号筛选只命中该实例下的任务（含同组两条），按表单编号筛选命中该表单下的全部实例，两种编号口径不混用（R2）；`lisi` 的两条同组待办在 API 中 `group_id` 相同且 `group_member_count=2`；页面显示同组提示（具体文案见 Q9），两条仍可分别打开和处理。
  2. 数据副作用：筛选/分页不改变任务状态；`outsider` 待办 `total=0`，看不到他人任务；实例单号与表单编号在列表/详情中分别展示、互不替代。
  3. 通知/审计副作用：无新增通知或动作。
- **反例/边界**：
  - “合并展示”的合并单位见 Q9；本用例的硬性断言是组信息一致且可分别操作，不把合并为一行作为通过条件。
- **自动化位置**：`testing/e2e/specs/approve.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q9

#### TASK-02 动作守卫

### TASK-02-a 正向：审批节点与填写节点的可用动作符合节点语义

- **需求来源**：PRD §3.3.2、F4.3；TECH §4.3 事件表；OpenAPI `POST /tasks/assignments/{assignment_id}/act`（action 枚举）
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人）、`wangwu`（填写节点处理人）。
  - 表单/流程版本与状态：发布流程 start → 审批节点 `A`(lisi，配置退回目标) → 填写节点 `F`(wangwu，开放补充字段) → end，绑定已发布表单。
  - 实例状态与数据：I1 停在 `A`，lisi 待办；I2 已过 `A`、停在 `F`，wangwu 待办（由 API 工厂分别创建）。
- **步骤**：
  1. `lisi` 打开 I1 的处理页，观察动作按钮。
  2. `lisi` 以 `AGREE` 处理 I1，填写意见。
  3. `wangwu` 打开 I2 的处理页，观察动作按钮。
  4. `wangwu` 以 `SUBMIT` 处理 I2，填写补充字段。
- **期望结果**：
  1. 页面/接口可观察结果：审批节点显示“同意/驳回/退回”，不显示“提交”；`AGREE` 成功后 I1 进入下一节点或 `APPROVED`；填写节点显示“提交/退回”，不显示“同意/驳回”；`SUBMIT` 成功后 I2 推进。
  2. 数据副作用：每次动作只产生 1 条动作记录、1 份快照；修改字段按节点权限落库；任务状态变为已办。
  3. 通知/审计副作用：对应后续处理人或发起人按通知矩阵收到通知；时间线记录动作、操作人、节点、意见、时间。
- **反例/边界**：
  - 填写节点是否支持意见/附件必填见 Q21；本用例只验证动作集合。
- **自动化位置**：`testing/e2e/specs/approve.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q21

### TASK-02-b 反向：越权、已处理、已取消、终态与非本节点动作一律拒绝且无副作用

- **需求来源**：PRD F4.3、§3.5.4；TECH §4.3 前置校验；OpenAPI `act` 契约；TEST-PLAN §6.6 TASK-02
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`、`lisi`、`wangwu`、`zhaoliu`。
  - 表单/流程版本与状态：发布包含审批节点与填写节点的流程；另建一条会签 any 流程用于产生已取消任务；终态实例由 API 工厂创建（已通过/已终止）。
  - 实例状态与数据：
    - I1：`RUNNING`，lisi 有一条 PENDING 审批指针。
    - I2：会签 any 中 lisi 已同意、wangwu 的任务已被取消。
    - I3：`APPROVED`，保留 lisi 的历史任务。
    - I4：`RUNNING`，填写节点 wangwu 待办。
- **步骤**：
  1. `wangwu` 以自己的身份对 lisi 在 I1 的 assignment 发起 `AGREE`。
  2. `lisi` 先对 I1 完成一次 `AGREE`，再用同一 assignment 重复 `AGREE`。
  3. `wangwu` 对 I2 中已取消的 assignment 发起 `AGREE`。
  4. `lisi` 对 I3 中的历史 assignment 发起 `AGREE`。
  5. `lisi` 对 I4 的填写节点 assignment 发起 `AGREE`；`wangwu` 用 `REJECT` 处理填写节点。
  6. 若流程节点配置 `opinion_required` 或 `attachment_required`，在缺失时发起动作。
- **期望结果**：
  1. 页面/接口可观察结果：以上请求全部返回结构化 4xx（越权建议 403/404，状态冲突/非法动作见 Q10）；I1 在步骤 1 后状态与任务不变；步骤 2 的重复动作不产生第二条已办；已取消/终态/非本节点动作不改变实例。
  2. 数据副作用：任务状态、实例状态、轮次、字段值、快照均不变；不新增动作记录；不产生后继任务。
  3. 通知/审计副作用：不新增通知；不新增审计动作。
- **反例/边界**：
  - 返回码的具体选择见 Q10；通过条件为“4xx + 错误体可读 + 无副作用”。
  - 意见/附件必填的适用节点见 Q21。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q21

#### TASK-03 会签 all / 或签 any

### TASK-03-a 会签 all 正向：全员同意后节点才通过

- **需求来源**：PRD §3.5.2、§3.5.3；TECH §4.3（AGREE 未满足聚合/节点完成）；TEST-PLAN §6.6 TASK-03
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`（会签成员）、`zhaoliu`（后继审批人）。
  - 表单/流程版本与状态：发布流程 start → 审批节点 `C`（assignee mode=ALL，来源 users: lisi、wangwu）→ 审批节点 `N`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，停在 `C`，lisi、wangwu 各 1 条待办。
- **步骤**：
  1. `lisi` 同意（意见“同意”）。
  2. 查询实例、wangwu 待办、zhaoliu 待办。
  3. `wangwu` 同意。
  4. 再次查询。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 2 时实例仍 `RUNNING`，进度显示 `C` 已完成 1/2；wangwu 待办仍在；zhaoliu 无待办；步骤 4 时 `C` 完成，`N` 生成且只生成 1 条 zhaoliu 待办。
  2. 数据副作用：lisi、wangwu 各 1 条已完成记录；不会在 lisi 同意后提前推进；不会永久停在 `C`；不会重复生成 `N` 任务。
  3. 通知/审计副作用：lisi 同意后不给 zhaoliu 发待办通知；wangwu 同意后 zhaoliu 收到 1 条新待办通知；时间线按动作顺序记录两条同意。
- **反例/边界**：
  - 若两人同时同意，仍只生成一个后继任务（并发场景见 TASK-06-c）。
- **自动化位置**：`testing/e2e/specs/parallel-countersign.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：无

### TASK-03-b 会签 all 反向：一人驳回导致整组失败、其余任务取消

- **需求来源**：PRD §3.5.3（任一子任务驳回/退回 → 组失败）、§3.5.4；TEST-PLAN §6.6 TASK-03
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`（会签成员）、`zhaoliu`（后继审批人）。
  - 表单/流程版本与状态：发布流程 start → 审批节点 `C`（ALL，lisi、wangwu，reject_policy=reject_to_initiator）→ `N`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，停在 `C`，双方待办。
- **步骤**：
  1. `lisi` 驳回，意见“资料不全”。
  2. `wangwu` 尝试同意。
  3. 查询实例、双方待办、zhaoliu 待办、发起人通知。
- **期望结果**：
  1. 页面/接口可观察结果：实例进入 `REJECTED`，`round` 仍为 1；`wangwu` 的同意请求被拒绝（结构化 4xx，见 Q10）；`wangwu` 待办为空或显示已取消；`zhaoliu` 从未收到 `N` 待办；发起人详情显示驳回意见与需修改字段。
  2. 数据副作用：`C` 组失败，所有 PENDING 任务取消；没有 `N` 任务；不产生 `APPROVED`；lisi 的驳回记录保留。
  3. 通知/审计副作用：发起人收到驳回通知；`wangwu` 收到“无需处理”类知会（形式见 Q11）；时间线记录驳回动作、意见与时间。
- **反例/边界**：
  - 被取消任务在“已办”中的归属见 Q11。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）；页面断言可补 `testing/e2e/specs/parallel-countersign.spec.ts`
- **需求待确认项**：Q10、Q11

### TASK-03-c 或签 any 正向：一人同意即通过，其余任务取消且不可再操作

- **需求来源**：PRD §3.5.3（任一同意 → 节点通过、自动取消其余子任务）、F4.5；TEST-PLAN §6.6 TASK-03
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`（或签成员）、`zhaoliu`（后继审批人）。
  - 表单/流程版本与状态：发布流程 start → 审批节点 `O`（assignee mode=ANY，lisi、wangwu）→ `N`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，停在 `O`，双方待办。
- **步骤**：
  1. `lisi` 同意。
  2. `wangwu` 打开待办并尝试同意。
  3. 查询实例、zhaoliu 待办、通知。
- **期望结果**：
  1. 页面/接口可观察结果：`lisi` 同意后 `O` 立即通过，`N` 生成且只生成 1 条 zhaoliu 待办；`wangwu` 待办消失或显示已取消，其同意请求被拒绝（结构化 4xx）。
  2. 数据副作用：`wangwu` 的 assignment 被取消，不能再处理；不会生成第二个 `N`；实例继续 `RUNNING` 或按后继到达终态。
  3. 通知/审计副作用：`wangwu` 收到“无需处理”知会并待办移除；`lisi` 的动作、`wangwu` 的取消均有记录；`zhaoliu` 收到 1 条新待办通知。
- **反例/边界**：
  - 取消知会的形式与已办归属见 Q11。
- **自动化位置**：`testing/e2e/specs/parallel-countersign.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q11

### TASK-03-d 或签 any 反向：先驳回则组失败，不得被后到的同意“救回”

- **需求来源**：PRD §3.5.3（任一子任务先驳回 → 组失败）、§3.5.4；TEST-PLAN §6.6 TASK-03
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`（或签成员）、`zhaoliu`（后继）。
  - 表单/流程版本与状态：发布流程 start → 审批节点 `O`（ANY，lisi、wangwu）→ `N`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，停在 `O`，双方待办。
- **步骤**：
  1. `lisi` 驳回。
  2. `wangwu` 在 `lisi` 驳回后同意。
  3. 查询实例状态、任务与后继。
- **期望结果**：
  1. 页面/接口可观察结果：实例为 `REJECTED`；`wangwu` 的请求被拒绝（结构化 4xx）；`N` 不存在；`zhaoliu` 无待办。
  2. 数据副作用：或签组失败，所有任务取消；不会因后到的同意而变为通过；`round` 不变。
  3. 通知/审计副作用：发起人收到驳回通知；`wangwu` 收到取消知会；时间线保留驳回与取消记录。
- **反例/边界**：
  - 若两个请求几乎同时到达，最终状态只能是“通过”或“驳回”之一，不能同时出现两组结果；并发见 TASK-06。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q11

#### TASK-04 并行组汇合

### TASK-04-a 并行组 all：两端都完成才汇合，不提前推进

- **需求来源**：PRD §3.3.2（并行组容器、聚合见 §3.5.3）、§3.5.3；TECH §4.3/§4.4；TEST-PLAN §6.6 TASK-04
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（成员 A 审批人）、`wangwu`（成员 B 填写人）、`zhaoliu`（组后审批人）。
  - 表单/流程版本与状态：发布流程 start → 并行组 `P`（mode=all，成员 A=审批 lisi、成员 B=填写 wangwu）→ 审批 `N`(zhaoliu) → end；B 开放一个补充字段。
  - 实例状态与数据：`RUNNING`，`P` 已激活，A、B 各 1 条待办。
- **步骤**：
  1. `lisi` 同意 A。
  2. 查询实例、`N` 待办、B 待办。
  3. `wangwu` 提交 B。
  4. 再次查询。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 2 时实例仍 `RUNNING`，`N` 不存在，B 仍待办；步骤 4 时并行组汇合，`N` 生成且只生成 1 条 zhaoliu 待办。
  2. 数据副作用：组内 A、B 各 1 条完成记录；不会提前推进，也不会永久卡住；不会重复生成 `N`。
  3. 通知/审计副作用：步骤 2 不给 zhaoliu 发待办通知；步骤 4 zhaoliu 收到 1 条；时间线记录两边完成与汇合。
- **反例/边界**：
  - 组内任一成员失败的处理见 TASK-04-c。
- **自动化位置**：`testing/e2e/specs/parallel-countersign.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：无

### TASK-04-b 并行组 any：首个成功即汇合，不永久卡住

- **需求来源**：PRD §3.3.2（并行组聚合模式 all/any、见 §3.5.3）；TECH 聚合语义；TEST-PLAN §6.6 TASK-04
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（成员 A）、`wangwu`（成员 B）、`zhaoliu`（组后审批人）。
  - 表单/流程版本与状态：发布流程 start → 并行组 `P`（mode=any，成员 A=审批 lisi、成员 B=审批 wangwu）→ `N`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，`P` 已激活，A、B 各 1 条待办。
- **步骤**：
  1. `lisi` 同意 A。
  2. 查询实例、`N` 待办、B 的待办/可操作性。
- **期望结果**：
  1. 页面/接口可观察结果：`lisi` 同意后组立即汇合，`N` 生成且只生成 1 条 zhaoliu 待办；实例不因 B 未处理而停留；B 的任务不得再生成第二个 `N`。
  2. 数据副作用：`P` 只汇合一次；`N` 任务唯一；B 的最终任务状态按 D-03 处理：整组取消、其余成员知会，不得影响主线。
  3. 通知/审计副作用：`zhaoliu` 收到 1 条新待办通知；B 的取消知会（若取消）按 Q11；时间线记录汇合。
- **反例/边界**：
  - 若产品确认 any 组汇合后不取消其余成员，则需明确 B 再处理时的行为；见 Q12。
- **自动化位置**：`testing/e2e/specs/parallel-countersign.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q11

### TASK-04-c 并行组反向：成员失败导致组失败且不产生后继

- **需求来源**：PRD §3.5.3（驳回 → 组失败）、§3.5.4；需求方确认 D-03（退回不按组失败）；TEST-PLAN §6.6 TASK-04
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（成员 A 审批人）、`wangwu`（成员 B 填写人）、`zhaoliu`（组后审批人）。
  - 表单/流程版本与状态：发布流程 start → 并行组 `P`（mode=all，成员 A=审批 lisi、成员 B=填写 wangwu）→ `N`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，`P` 已激活，A、B 各 1 条待办。
- **步骤**：
  1. `lisi` 驳回 A。
  2. `wangwu` 尝试提交 B。
  3. 查询实例、`N`、双方任务。
- **期望结果**：
  1. 页面/接口可观察结果：实例进入 `REJECTED`（按驳回策略）；`N` 不存在；`wangwu` 的提交被拒绝（结构化 4xx）。
  2. 数据副作用：并行组失败，其余 PENDING 任务取消；不产生部分推进或“半汇合”；`round` 不变。
  3. 通知/审计副作用：发起人收到驳回通知；`wangwu` 收到取消知会；时间线记录失败与取消。
- **反例/边界**：
  - 并行组成员“退回”的语义见 D-03 和 TASK-04-d；本用例只覆盖“驳回”。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q11

### TASK-04-d 并行组成员退回：取消整组并重派，实例保持 RUNNING（D-03）

- **需求来源**：PRD §3.5.4；TECH §4.4；需求方确认 D-03；TEST-PLAN §6.6 TASK-04、§6.7 RETURN-01
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（A 审批人）、`wangwu`（B 审批人）、`zhaoliu`（C 审批人）、`admin`（D 审批人）。
  - 表单/流程版本与状态：发布流程 start → A(lisi) → 并行组 P（mode=all，B=wangwu、C=zhaoliu）→ D(admin) → end；C 的 `return_targets=[A]`。
  - 实例状态与数据：`RUNNING`，P 已激活，B、C 各有 1 条待办。
- **步骤**：
  1. `zhaoliu` 退回至 A，意见“并行组退回”。
  2. 查询实例状态、B/C/D 的任务、待办与时间线。
  3. `lisi` 重新处理 A 并同意，观察后续。
- **期望结果**：
  1. 页面/接口：实例仍为 `RUNNING`，不进入 `REJECTED`；P 组整体取消（B、C 的待办消失，任务状态为取消），D 不生成任务。
  2. 数据副作用：A 生成新的待办给 `lisi`；已填数据保留不回滚；不产生重复的任务或“半汇合”。
  3. 通知/审计副作用：`wangwu` 收到“无需处理”知会；`lisi` 收到新待办通知；时间线记录退回人、目标节点、原因与整组取消。
- **反例/边界**：
  - `wangwu` 在 C 退回后尝试提交 B：返回结构化 4xx，不产生部分推进或“救回”。
  - 退回目标在 P 之前：按 D-03 整组重派，不保留组内已同意成员。
- **自动化位置**：`testing/e2e/specs/reject-resubmit.spec.ts` + `backend/tests/test_acceptance_execution.py`
- **需求待确认项**：Q10、Q14

#### TASK-05 处理意见/附件/字段修改

### TASK-05-a 正向：意见、附件、可编辑字段修改与 diff/快照齐全

- **需求来源**：PRD F4.3、F4.4、§3.6；TECH §4.5（字段补丁）与快照；TEST-PLAN §6.6 TASK-05、§6.4 PERM-04
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人）、运行内创建 `E2E-<runId>-outsider`（无关用户）。
  - 表单/流程版本与状态：发布表单含 `amount`（数字，发起时必填）、`remark`（文本，审批节点可编辑）、`supplement`（文本，发起隐藏、审批节点可编辑）、`files`（附件）；发布流程 start → 审批 `N1`(lisi) → end。
  - 实例状态与数据：`zhangsan` 已提交，`amount=100`、`remark="old"`；`lisi` 有 1 条 PENDING 待办；`lisi` 已上传 1 个临时附件。
- **步骤**：
  1. `lisi` 打开详情，修改 `remark` 与 `supplement`，添加附件，填写意见“同意”，执行同意。
  2. 查询实例数据、时间线、快照、附件。
  3. `zhangsan` 与 `lisi` 下载该附件；`E2E-<runId>-outsider` 尝试下载。
- **期望结果**：
  1. 页面/接口可观察结果：实例变为 `APPROVED`；`remark`、`supplement` 更新；`amount` 不变；时间线显示意见与附件，字段变更以“旧值 → 新值”呈现；提交动作快照包含新值与附件元数据。
  2. 数据副作用：只有可编辑字段被修改；diff 记录操作人、节点、时间、字段新旧值；附件绑定到实例。
  3. 通知/审计副作用：发起人收到结果通知；`zhangsan`、`lisi` 可下载附件；`outsider` 下载被拒（403/404）；无越权数据泄露。
- **反例/边界**：
  - 抄送人的附件权限按 R4（可见字段附件可下载，hidden 字段附件不可见）；本用例不涉及抄送。
  - 填写节点的意见/附件必填见 Q21。
- **自动化位置**：`testing/e2e/specs/approve.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q21

### TASK-05-b 反向：只读/隐藏字段篡改不落库，越权附件下载被拒

- **需求来源**：PRD F4.3、PERM-02；PHASE2 §3.4（隐藏字段非法修改不落库）；TEST-PLAN §6.6 TASK-05
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人）、`wangwu`（无关用户，非参与者）。
  - 表单/流程版本与状态：发布表单含 `amount`（审批节点只读）、`hidden_note`（审批节点隐藏）、`remark`（审批节点可编辑）、`files`（附件）；发布流程 start → 审批 `N1`(lisi) → end。
  - 实例状态与数据：`zhangsan` 已提交，`amount=100`；`lisi` 有 PENDING 待办并已上传 1 个附件；另有一个终态实例保留历史任务。
- **步骤**：
  1. `lisi` 在 `field_patch` 中传入 `amount=9999`、`hidden_note="泄露"`、`remark="ok"`，执行同意。
  2. 查询实例数据、时间线、快照。
  3. `wangwu` 下载 `lisi` 的附件；`wangwu` 对实例详情发起访问。
  4. `zhangsan` 对 `lisi` 的 assignment 发起动作（发起人不是处理人）。
- **期望结果**：
  1. 页面/接口可观察结果：`amount` 保持 100；`hidden_note` 的值不出现在实例数据、快照、时间线或响应中；`remark` 正常更新；若请求因非法字段被整单拒绝，则 `remark` 也不得更新（见 Q23）；越权附件下载返回 403/404；`wangwu` 访问详情返回 403/404；`zhangsan` 处理他人任务被拒。
  2. 数据副作用：非法字段值一律不落库；不产生额外动作/快照；实例状态只按合法动作变化。
  3. 通知/审计副作用：失败请求不产生通知或审计动作；成功请求只记录合法字段变更。
- **反例/边界**：
  - “整单拒绝 vs 静默过滤”见 Q23；本用例的硬性断言是非法值不落库、不泄露。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q23

#### TASK-06 并发与重复操作

### TASK-06-a 同一人双击/网络重放同一动作：只生效一次

- **需求来源**：OpenAPI `act` 描述（`X-Request-Id` 重放返回同一结果）；TECH §3.4（`request_id` 唯一索引、同人同任务唯一键）；TEST-PLAN §6.6 TASK-06
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人）、`wangwu`（后继审批人）。
  - 表单/流程版本与状态：发布流程 start → 审批 `N1`(lisi) → 审批 `N2`(wangwu) → end。
  - 实例状态与数据：`RUNNING`，停在 `N1`，lisi 有 1 条 PENDING；记录当前实例版本。
- **步骤**：
  1. 用相同的 `X-Request-Id`、相同 `expected_version` 连续发送 2 次 `AGREE`。
  2. 查询任务、时间线、快照、通知。
- **期望结果**：
  1. 页面/接口可观察结果：两次响应结果一致（均成功，或第二次返回同一结果）；实例只推进一次；`N2` 只生成 1 条待办。
  2. 数据副作用：只产生 1 条动作记录、1 份快照、1 条已办；没有重复任务；没有重复字段变更。
  3. 通知/审计副作用：`wangwu` 只收到 1 条新待办通知；审计只记录 1 次动作。
- **反例/边界**：
  - 若客户端未带相同 `X-Request-Id`，但同一 assignment 已处理，第二次仍必须被状态守卫拒绝；见 TASK-02-b。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：无（重放语义由 OpenAPI 明确）

### TASK-06-b 同一人两个标签页并发不同动作：一个生效，另一个 409

- **需求来源**：TECH §3.4（乐观锁 `expected_version`、409 `STALE_VERSION`）；OpenAPI `act` 描述（版本不符 409）；TEST-PLAN §6.6 TASK-06、§10.2
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人）。
  - 表单/流程版本与状态：发布流程 start → 审批 `N1`(lisi) → end。
  - 实例状态与数据：`RUNNING`，lisi 有 1 条 PENDING；两个标签页都读取到同一个 `expected_version=v`。
- **步骤**：
  1. 标签页 A 以 `AGREE`、`expected_version=v` 处理。
  2. 标签页 B 以 `REJECT`、`expected_version=v` 处理（在 A 之后或并发）。
  3. 查询实例状态、动作、快照、通知。
- **期望结果**：
  1. 页面/接口可观察结果：A 生效；B 返回 409（版本不符，见 TECH/OpenAPI）或结构化状态冲突 4xx；最终实例状态与 A 的动作一致（`APPROVED` 或推进），不会同时出现“已通过 + 已驳回”。
  2. 数据副作用：只有 1 条动作记录、1 份快照；B 不修改字段、不取消任务、不产生后继。
  3. 通知/审计副作用：只产生与 A 对应的通知；B 不产生通知或审计动作。
- **反例/边界**：
  - 若两个请求真正同时到达，服务端串行化后仍只能有一个赢家；不得 500。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10（若实际未返回 409）

### TASK-06-c 两个会签人并发同意：两次动作都记录，节点只完成一次

- **需求来源**：PRD §3.5.2、§7（并发提交不产生重复任务）；TECH §4.3（节点完成与后继生成）；TEST-PLAN §6.6 TASK-06、§10.2
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`（会签成员）、`zhaoliu`（后继审批人）。
  - 表单/流程版本与状态：发布流程 start → 审批 `C`（ALL，lisi、wangwu）→ `N`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，停在 `C`，双方各 1 条 PENDING。
- **步骤**：
  1. 并发发送 lisi 与 wangwu 的 `AGREE`。
  2. 查询任务、后继、时间线、快照。
- **期望结果**：
  1. 页面/接口可观察结果：两个请求都成功（或一个成功、另一个返回“已处理”类 4xx，见 Q10）；节点 `C` 只完成一次；`N` 只生成 1 条 zhaoliu 待办。
  2. 数据副作用：lisi、wangwu 各 1 条已完成记录；不会因并发只记录一人；不会重复生成 `N`；不会出现“组已完成但仍有人待办”的脏状态。
  3. 通知/审计副作用：zhaoliu 只收到 1 条新待办通知；两条同意动作各留审计；无重复通知。
- **反例/边界**：
  - 若实现串行化后第二个请求读到“组已完成”并拒绝，则该请求不得产生副作用；通过条件是数据唯一且可解释。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10

#### TASK-07 转办/委托

### TASK-07-a 转办正向：待办转移、原处理人留痕且仍可见、目标人可处理

- **需求来源**：PHASE3 §4.1、§4.4、§4.5、§4.7；TEST-PLAN §6.6 TASK-07；OpenAPI `POST /tasks/assignments/{assignment_id}/transfer`
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（原处理人）、`wangwu`（转办目标，启用、非同一任务已有待办）。
  - 表单/流程版本与状态：发布流程 start → 审批 `N1`(lisi) → 审批 `N2`(zhaoliu) → end。
  - 实例状态与数据：`RUNNING`，停在 `N1`，lisi 有 1 条 PENDING；`wangwu` 无该实例的 assignment。
- **步骤**：
  1. `lisi` 调用转办，`to_user_id=wangwu`，`reason="出差"`。
  2. 查询 `lisi` 的待办/已办、`wangwu` 的待办、实例详情与时间线、通知。
  3. `wangwu` 打开详情并同意。
- **期望结果**：
  1. 页面/接口可观察结果：`lisi` 待办消失，已办出现“已转办”记录；`wangwu` 待办出现该任务；`wangwu` 具备该节点原有字段权限并可同意；实例详情/时间线显示“lisi 转办给 wangwu”及原因；`lisi` 仍能查看实例详情（历史参与人）。
  2. 数据副作用：原 assignment 取消（原因 TRANSFERRED），为目标人新建同任务同序号的待办；节点、令牌与聚合规则不变；实例状态不因转办而推进。
  3. 通知/审计副作用：`wangwu` 与 `lisi` 各收到 `TASK_TRANSFERRED` 类通知（PHASE3 §4.5）；时间线与操作审计包含转办记录与原因。
- **反例/边界**：
  - 会签组中一人转办后组结构不变；本用例为单审批，组场景由 TASK-07-b 的撞重夹具覆盖。
- **自动化位置**：`testing/e2e/specs/transfer-delegation.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：无

### TASK-07-b 转办反向：撞重、越权、非待办、停用目标与空原因被拒

- **需求来源**：PHASE3 §4.1（转办规则）、§4.7；TEST-PLAN §6.6 TASK-07；OpenAPI `TransferRequest`（reason minLength=1）
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`lisi`（原处理人）、`wangwu`（会签同任务同序号已有待办的人）、`zhaoliu`（非管理员、非本人）、`admin`（管理员）、运行内创建 `E2E-<runId>-disabled`（停用用户）。
  - 表单/流程版本与状态：发布会签流程 start → 审批 `C`（ALL，lisi、wangwu）→ end；发布普通流程用于已完成任务与管理员代转。
  - 实例状态与数据：
    - I1：`RUNNING`，`C` 中 lisi、wangwu 各 1 条 PENDING（同任务同序号）。
    - I2：`RUNNING`，lisi 有 PENDING。
    - I3：lisi 的任务已完成或已取消。
- **步骤**：
  1. `lisi` 将 I1 的任务转给 `wangwu`（撞重）。
  2. `lisi` 将 I2 的任务转给自己。
  3. `lisi` 将 I2 的任务转给停用用户。
  4. `zhaoliu` 尝试转办 lisi 在 I2 的任务。
  5. `lisi` 尝试转办 I3 中已完成/已取消的任务。
  6. `lisi` 提交 `reason=""` 的转办请求。
  7. `admin` 代为转办 lisi 在 I2 的任务给 `wangwu`。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1–6 全部返回结构化 4xx（空原因按契约 422）；lisi 的原 assignment 仍为 PENDING；wangwu 不会因此新增待办；停用用户不获得任务；`zhaoliu` 无权操作。步骤 7 成功：lisi 的 assignment 取消，wangwu 获得待办。
  2. 数据副作用：失败请求不改变任务/实例/组结构，不新增/取消 assignment；步骤 7 只新增一条目标待办并写转办记录。
  3. 通知/审计副作用：失败请求不产生通知/审计；步骤 7 通知双方并写审计。
- **反例/边界**：
  - 管理员代转的“操作人”记录应可追溯；具体展示见 Q10 之外的文档，本用例只要求审计中包含管理员与目标人。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10

### TASK-07-c 委托正向：窗口内新任务派给被委托人，委托人仍可见

- **需求来源**：PHASE3 §4.2、§4.4、§4.5、§4.7；TEST-PLAN §6.6 TASK-07；OpenAPI `POST /delegations`
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`lisi`（委托人，审批人）、`wangwu`（被委托人，启用）、`zhangsan`（发起人）；`admin`。
  - 表单/流程版本与状态：发布流程 start → 审批 `N1`(lisi) → end；另有一条流程用于验证“已有待办不自动转交”。
  - 实例状态与数据：`lisi` 创建生效中的委托：`delegatee=wangwu`、`start_at=now-1min`、`end_at=now+2h`、`reason="休假"`、`flow_template_ids=null`；在委托生效前创建实例 I_old 并已有 lisi 待办；委托生效后由 `zhangsan` 新建实例 I_new。
- **步骤**：
  1. `lisi` 创建委托，查询委托列表。
  2. `zhangsan` 提交 I_new。
  3. 查询 `wangwu` 待办、`lisi` 待办、I_new 详情、通知、审计与时间线。
  4. `wangwu` 同意 I_new。
- **期望结果**：
  1. 页面/接口可观察结果：I_new 的 `N1` 待办派给 `wangwu`，详情显示代理关系（委托人 lisi、被委托人 wangwu、原因）；`lisi` 不显示该待办但仍能查看详情；I_old 的待办仍在 lisi 处（不自动转交）。
  2. 数据副作用：委托只影响新派发任务；I_new 的任务处理人为 wangwu，节点权限不变；`wangwu` 可正常同意并推进；委托列表状态 `ACTIVE`。
  3. 通知/审计副作用：`wangwu` 与 `lisi` 收到 `TASK_DELEGATED` 类通知；操作审计记录 `DELEGATE`；实例时间线不记录“创建委托”（委托是用户配置变更，按 PHASE3 §4.5 只写操作审计）。
- **反例/边界**：
  - 若 `wangwu` 已在同一任务有 pending，委托跳过并通知委托人“委托未生效”；见 TASK-07-d。
  - 时区与窗口端点口径见 Q24。
- **自动化位置**：`testing/e2e/specs/transfer-delegation.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q24

### TASK-07-d 委托反向与边界：重叠、自委托、时间非法、停用、到期与撞重

- **需求来源**：PHASE3 §4.2（委托规则与边界）、§4.7；TEST-PLAN §6.6 TASK-07；OpenAPI `DelegationCreate`
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`lisi`（委托人）、`wangwu`（被委托人）、`zhaoliu`（另一用户）、运行内创建 `E2E-<runId>-disabled`（停用用户）、`admin`。
  - 表单/流程版本与状态：发布流程 start → 审批 `N1`(lisi) → end；另建一条会签流程，使 lisi 与 wangwu 是同一节点/同一任务的成员，用于撞重。
  - 实例状态与数据：`lisi` 已有一条生效中的全流程委托给 `wangwu`（[t1,t2)）；无其他待办冲突。
- **步骤**：
  1. `lisi` 创建与现有委托时间重叠的第二条委托。
  2. `lisi` 创建 `delegatee=lisi` 的委托。
  3. `lisi` 创建 `end_at <= start_at` 的委托。
  4. `lisi` 创建 `delegatee` 为停用用户的委托。
  5. `lisi` 创建限定另一流程、但与现有委托时间重叠的委托。
  6. 创建已过期委托（[now-2h, now-1h)），再由 `zhangsan` 发起新实例。
  7. 在 lisi、wangwu 同为会签成员的实例上，派发给 lisi 的 assignment 命中委托但 wangwu 已在同一任务有 pending。
  8. `admin` 取消 `lisi` 的生效委托，再由 `zhangsan` 发起新实例。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1–5 均返回结构化 4xx（时间非法/原因缺失按契约 422），不生成委托记录；步骤 6 新任务派给 lisi，不派给 wangwu；步骤 7 跳过委托、任务按原处理人 lisi 派发，并通知 lisi“委托未生效”；步骤 8 取消成功，之后新任务回到 lisi。
  2. 数据副作用：失败请求不改变委托列表与任务派发；到期/取消不回溯修改已派出的待办（按 PHASE3 §4.2“已派出的待办不回退”对到期的表述；取消场景见 Q24）；撞重不产生额外 assignment。
  3. 通知/审计副作用：无效委托不产生通知；有效委托/取消写操作审计；撞重时仅向 lisi 发“未生效”通知（PHASE3 §4.2）。
- **反例/边界**：
  - 重叠端点是否含首尾、时区口径、取消后已派出待办的处理见 Q24；本用例使用明确不重叠/完全过期的时间窗，避免端点歧义。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q24

### 2.3 驳回、退回、撤回与终止

#### REJECT-01 驳回发起人后重提

### REJECT-01-a 驳回后重提：轮次+1、全流程重走、意见/旧快照/变更对照可查

- **需求来源**：PRD §3.5.1、§3.5.4、F3.6；TECH §4.3（RESUBMIT）；TEST-PLAN §6.7 REJECT-01；DEMO §2.4
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（N1）、`wangwu`（N2）、`zhaoliu`（N3）。
  - 表单/流程版本与状态：发布表单含 `reason`（发起可编辑、必填）、`amount`（发起可编辑）、`supplement`（发起隐藏、N2 可编辑）；发布流程 start → `N1`(lisi) → `N2`(wangwu) → `N3`(zhaoliu) → end；N2 的 `reject_policy=reject_to_initiator`。
  - 实例状态与数据：`RUNNING`，已过 N1、停在 N2；`reason="首轮"`、`amount=100`；N2 由 wangwu 待办。
- **步骤**：
  1. `wangwu` 驳回，意见“发票不全，请补齐”。
  2. `zhangsan` 打开详情，查看驳回意见、可编辑字段与历史快照。
  3. `zhangsan` 修改 `reason`、`amount`，并在请求中尝试修改 `supplement`；重新提交。
  4. 查询实例、任务、时间线、快照与快照 diff。
- **期望结果**：
  1. 页面/接口可观察结果：驳回后状态“已驳回”（`REJECTED`），`round=1`；详情顶部显示驳回意见与“修改并重新提交”入口；可编辑字段与首轮一致；`supplement` 不在可编辑集合。重提后状态 `RUNNING`、`round=2`；进度从 `N1` 重新开始，生成 lisi 的新待办。
  2. 数据副作用：驳回时所有 PENDING 任务取消（N2 取消，N3 从未生成）；重提不修改不可编辑字段 `supplement`（过滤或整单拒绝，见 Q23）；只有 1 个实例、`code` 不变；旧轮任务/动作保留为历史。
  3. 通知/审计副作用：驳回通知发给发起人；重提后 lisi 收到新待办通知；时间线包含驳回、重提；旧快照可查且内容不变；快照 diff 能显示 `reason`/`amount` 的旧值→新值，不显示 `supplement` 变更。
- **反例/边界**：
  - 仅可编辑字段可改、隐藏字段注入见 Q23；本用例的硬性断言是不可编辑字段不落库。
- **自动化位置**：`testing/e2e/specs/reject-resubmit.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q23

### REJECT-01-b 反向：非 REJECTED/非发起人/非法字段修改的重提被拒且无副作用

- **需求来源**：PRD §3.5.1、F3.6；TECH §4.3（RESUBMIT 前置 status=REJECTED）；TEST-PLAN §6.7 REJECT-01
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人）、`admin`；另建流程配置 `reject_policy=reject_forbidden`。
  - 表单/流程版本与状态：发布流程 start → 审批(lisi) → end；含 `reject_forbidden` 流程。
  - 实例状态与数据：分别准备 `RUNNING`、`DRAFT`、`APPROVED`、`WITHDRAWN`、`TERMINATED`、`REJECTED` 的实例；`REJECTED` 实例属于 zhangsan。
- **步骤**：
  1. `zhangsan` 对 `RUNNING`、`DRAFT`、`APPROVED`、`WITHDRAWN`、`TERMINATED` 实例调用重提。
  2. `lisi` 与 `admin` 分别对 `REJECTED` 实例调用重提。
  3. `zhangsan` 对 `REJECTED` 实例重提，但请求中修改一个发起阶段不可编辑字段。
  4. 在 `reject_forbidden` 流程的审批任务上尝试驳回（Q22）。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1–2 全部返回结构化 4xx（越权建议 403/404；状态非法见 Q10），实例状态、轮次、任务、快照不变；步骤 3 若请求成功，不可编辑字段不落库，若请求被拒则保持 `REJECTED`；步骤 4 的驳回按 Q22 确认的可见行为被拒绝或按钮不可用。
  2. 数据副作用：不产生新任务、不增加轮次、不写重提动作；合法重提能力仍保留。
  3. 通知/审计副作用：失败请求不产生通知/审计；不会重置轮次或重复派发。
- **反例/边界**：
  - `reject_forbidden` 的 UI/接口行为见 Q22；本用例只要求“不可驳回且无副作用”。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q22、Q23

### REJECT-01-c 连续多轮驳回重提：轮次递增、历史快照不可变

- **需求来源**：PRD F3.6（轮次递增、旧快照可查）、§3.6；TECH §4.3（RESUBMIT）；TEST-PLAN §6.7 REJECT-01
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（N1）、`wangwu`（N2）。
  - 表单/流程版本与状态：发布流程 start → `N1`(lisi) → `N2`(wangwu) → end；N1/N2 均允许驳回。
  - 实例状态与数据：`RUNNING`，停在 N1。
- **步骤**：
  1. `lisi` 驳回第 1 轮；`zhangsan` 重提；记录第 1 轮提交快照 S1。
  2. `lisi` 同意；`wangwu` 在 N2 驳回第 2 轮；`zhangsan` 重提；记录第 2 轮提交快照 S2。
  3. 查询实例、轮次、历史任务与快照 S1/S2、快照 diff。
- **期望结果**：
  1. 页面/接口可观察结果：轮次依次为 1 → 2 → 3；每次重提都从 N1 重新派发；同一实例 `code` 不变；“我发起的”中仍为 1 条。
  2. 数据副作用：每轮只保留当时有效的任务；旧轮任务为历史，不再 PENDING；S1 在后续轮次后内容不变；S2 可按轮次区分；旧快照与 diff 可查。
  3. 通知/审计副作用：每次驳回通知发起人、每次重提通知 N1 处理人；时间线按“驳回—重提—同意—驳回—重提”顺序记录；无重复实例。
- **反例/边界**：
  - 旧快照的“不可变”指后续动作不得改写其数据；如实现采用复制式快照或版本化快照均可，验收看查询结果。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：无

#### RETURN-01 退回指定前序节点

### RETURN-01-a 退回前序节点：数据不回滚、前序不重走、目标节点重派

- **需求来源**：PRD §3.5.1、§3.5.4；TECH §4.3（RETURN）、§4.4（取消规则）；TEST-PLAN §6.7 RETURN-01
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（A）、`wangwu`（B）、`zhaoliu`（C）、运行内创建 `E2E-<runId>-d`（D）。
  - 表单/流程版本与状态：发布表单含 `b_remark`（B 可编辑）；发布流程 start → `A`(lisi) → `B`(wangwu) → `C`(zhaoliu) → `D`(E2E-d) → end；C 的 `return_targets` 预配置为 [A, B]。
  - 实例状态与数据：`RUNNING`，已过 A、B，停在 C；B 填写 `b_remark="B已填"`；C 由 zhaoliu 待办。
- **步骤**：
  1. `zhaoliu` 调用 `GET /tasks/assignments/{aid}/return-targets`，确认目标集合。
  2. `zhaoliu` 退回至 B，意见“补充说明”。
  3. 查询实例状态、A/B/C/D 的任务、数据、时间线、通知。
- **期望结果**：
  1. 页面/接口可观察结果：可退回目标包含 A、B，不包含 C（自身）与 D（后继）；退回后实例仍为 `RUNNING`；C 任务取消；D 不存在；B 生成新的待办给 wangwu；A 不重新派发；A、B 的历史已完成记录保留。
  2. 数据副作用：`b_remark` 与其他已填数据保持不变（不回滚）；B 新任务拥有 B 节点原有字段权限；不会出现重复的 A 任务或 D 任务。
  3. 通知/审计副作用：wangwu 收到新待办通知；时间线记录退回动作、目标节点、意见与操作人；发起人可按可见性查看。
- **反例/边界**：
  - 若退回目标在并行组之前导致整组重派：按 D-03 整组重派；本用例的流程无并行组，见 TASK-04-d。
  - 下游已填数据/旧任务在已办的呈现见 Q14。
- **自动化位置**：`testing/e2e/specs/reject-resubmit.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q14

### RETURN-01-b 反向：非法退回目标、越权与终态实例被拒且无副作用

- **需求来源**：PRD §3.5.4（退回目标为预配置前序节点集合）；TECH §4.3（`target ∈ allowed_return_targets()`）；TEST-PLAN §6.7 RETURN-01
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（A）、`wangwu`（B）、`zhaoliu`（C）、`admin`。
  - 表单/流程版本与状态：发布流程 start → A → B → C → end；C 的 `return_targets` 仅配置 [B]。
  - 实例状态与数据：`RUNNING`，停在 C，zhaoliu 待办；另有 `APPROVED`、`TERMINATED`、`WITHDRAWN` 实例。
- **步骤**：
  1. `zhaoliu` 尝试退回到自身 C。
  2. `zhaoliu` 尝试退回到后继节点（若流程有 D）或不存在的节点 ID。
  3. `zhaoliu` 尝试退回到未配置的 A（仅 B 合法）。
  4. `wangwu`（非当前处理人）尝试退回 C 的任务。
  5. `zhaoliu` 对终态实例的历史任务发起退回。
  6. 若接口允许缺省 `return_target`，尝试不传目标（Q13）。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1–6 全部返回结构化 4xx（越权建议 403/404，目标非法见 Q10）；C 的任务仍为 PENDING、仍属 zhaoliu；实例状态仍 `RUNNING`。
  2. 数据副作用：不取消任务、不重派目标、不回滚数据、不改变时间线；终态实例保持终态。
  3. 通知/审计副作用：失败请求不产生通知/审计；无新待办。
- **反例/边界**：
  - 缺省目标的默认行为见 Q13；本用例的硬性断言是“非法目标/越权一律拒绝且无副作用”。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10

#### WITHDRAW-01 撤回

### WITHDRAW-01-a 正向：无人处理时可撤回，任务取消、相关人知会

- **需求来源**：PRD §3.5.4（撤回条件与效果）、F4.5；TECH §4.3（WITHDRAW）；TEST-PLAN §6.7 WITHDRAW-01
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（N1）、`wangwu`（N2）。
  - 表单/流程版本与状态：发布流程 start → `N1`(lisi) → `N2`(wangwu) → end。
  - 实例状态与数据：`RUNNING`，停在 N1，lisi 有 PENDING；没有任何任务被处理过。
- **步骤**：
  1. `zhangsan` 提交撤回请求（可附原因）。
  2. 查询实例、lisi 待办、时间线、通知。
  3. `lisi` 尝试处理该任务；`zhangsan` 尝试重提。
- **期望结果**：
  1. 页面/接口可观察结果：实例变为 `WITHDRAWN`（页面“已撤回”）；lisi 待办移除；lisi 处理请求被拒；`zhangsan` 重提被拒（`WITHDRAWN` 为终态，重提仅允许 `REJECTED`）。
  2. 数据副作用：所有 PENDING 任务取消；不产生后继任务；实例数据保留可查看；`round` 不变。
  3. 通知/审计副作用：lisi 收到任务取消知会（F4.5）；时间线记录撤回操作人、时间、原因；发起人可见终态详情。
- **反例/边界**：
  - 撤回原因是否必填：OpenAPI `WithdrawRequest.reason` 非必填，按可选处理。
- **自动化位置**：`testing/e2e/specs/approve.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q14、Q15

### WITHDRAW-01-b 反向：已有任务被处理后不可撤回；非发起人不可撤回

- **需求来源**：PRD §3.5.4（尚无任何任务被处理过才可撤回）；TECH §4.3（WITHDRAW 守卫：不存在 DONE assignment）；TEST-PLAN §6.7 WITHDRAW-01
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（N1）、`wangwu`（N2）、`admin`。
  - 表单/流程版本与状态：发布流程 start → N1(lisi) → N2(wangwu) → end。
  - 实例状态与数据：`RUNNING`，lisi 已同意（存在 DONE assignment），停在 N2，wangwu 待办。
- **步骤**：
  1. `zhangsan` 尝试撤回。
  2. `lisi` 尝试撤回（非发起人）。
  3. `admin` 尝试撤回（管理员，非发起人）。
  4. 查询实例与任务。
- **期望结果**：
  1. 页面/接口可观察结果：三次请求均返回结构化 4xx（非发起人建议 403/404，状态冲突见 Q10）；页面不显示撤回入口或提示不可撤回。
  2. 数据副作用：实例仍 `RUNNING`；wangwu 的待办仍在；不取消任务、不改变轮次与数据。
  3. 通知/审计副作用：无撤回通知或审计动作。
- **反例/边界**：
  - 管理员应使用终止而非撤回；见 TERMINATE-01。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q15

### WITHDRAW-01-c 边界：抄送已读不算“任务被处理过”，仍可撤回

- **需求来源**：TECH §4.3（WITHDRAW 守卫：抄送已读不算）、PRD §3.5.4；TEST-PLAN §6.7 WITHDRAW-01
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`E2E-<runId>-cc`（抄送人）、`lisi`（审批人）。
  - 表单/流程版本与状态：发布流程 start → 抄送节点（cc_to=E2E-cc）→ 审批 `N1`(lisi) → end；抄送节点派发后主线继续。
  - 实例状态与数据：`RUNNING`，停在 N1；抄送任务已生成，`E2E-cc` 已标记已读；无审批 DONE。
- **步骤**：
  1. 确认抄送任务的 `is_read=true`。
  2. `zhangsan` 撤回。
  3. 查询实例、lisi 待办、抄送任务。
- **期望结果**：
  1. 页面/接口可观察结果：撤回成功，实例 `WITHDRAWN`；N1 任务取消；抄送任务保持已读/不再阻塞；抄送人仍可按可见性查看详情。
  2. 数据副作用：抄送已读不计入“处理过”的守卫，不阻止撤回；不产生审批结论或后继任务。
  3. 通知/审计副作用：lisi 收到取消知会；时间线记录撤回；抄送已读记录保留。
- **反例/边界**：
  - 若产品确认“抄送已读也算处理过”，需回写 PRD 并调整本用例；见 Q15。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q15

#### TERMINATE-01 终止

### TERMINATE-01-a 正向：管理员终止运行中实例，任务取消、相关人通知、原因留痕

- **需求来源**：PRD §3.5.4（终止：平台管理员、原因写入审计）、F4.5；TECH §4.3（TERMINATE）；TEST-PLAN §6.7 TERMINATE-01
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`admin`（平台管理员）、`zhangsan`（发起人）、`lisi`（当前处理人）、`wangwu`（后续处理人）。
  - 表单/流程版本与状态：发布流程 start → N1(lisi) → N2(wangwu) → end。
  - 实例状态与数据：`RUNNING`，停在 N1，lisi 待办。
- **步骤**：
  1. `admin` 调用终止，`reason="业务取消"`。
  2. 查询实例、lisi 待办、通知、时间线、操作审计。
  3. `lisi` 尝试处理；`zhangsan` 尝试重提或撤回。
- **期望结果**：
  1. 页面/接口可观察结果：实例变为 `TERMINATED`（页面“已终止”），`terminated_reason="业务取消"`；lisi 待办移除；lisi 处理请求被拒；发起人不能重提/撤回。
  2. 数据副作用：所有 PENDING 任务取消；不产生后继任务；实例数据保留只读；不删除实例。
  3. 通知/审计副作用：发起人、当前处理人等相关人员收到终止通知（范围见 Q16）；时间线与操作审计包含管理员、时间、原因；终止动作只记录一次。
- **反例/边界**：
  - 终止 DRAFT 是否允许见 Q16；本用例使用 RUNNING。
- **自动化位置**：`testing/e2e/specs/approve.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q16

### TERMINATE-01-b 反向：非管理员、终态实例、空原因被拒且无副作用

- **需求来源**：PRD §3.5.4（仅平台管理员、终态不可）、PRD §2；TECH §5.2（AdminUser）；OpenAPI `TerminateRequest.reason`（minLength=1）；TEST-PLAN §6.7 TERMINATE-01
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（处理人）、`zhaoliu`（设计者，非管理员）、`admin`。
  - 表单/流程版本与状态：发布流程 start → 审批(lisi) → end。
  - 实例状态与数据：`RUNNING` 实例；`APPROVED`、`WITHDRAWN`、`TERMINATED` 终态实例。
- **步骤**：
  1. `zhangsan` 终止 RUNNING 实例。
  2. `lisi` 终止 RUNNING 实例。
  3. `zhaoliu`（设计者）终止 RUNNING 实例。
  4. `admin` 对 `APPROVED`、`WITHDRAWN`、`TERMINATED` 实例发起终止。
  5. `admin` 以空字符串/缺失 `reason` 终止。
  6. 查询实例与任务。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1–4 返回结构化 4xx（非管理员建议 403，终态冲突见 Q10）；步骤 5 按契约返回 422；RUNNING 实例保持原状态与待办，终态实例不被改写。
  2. 数据副作用：不取消任务、不改变 `terminated_reason`、不写终止动作；无实例数据变更。
  3. 通知/审计副作用：失败请求不产生终止通知或审计动作。
- **反例/边界**：
  - DRAFT 终止是否允许见 Q16；本用例不断言 DRAFT。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q16

### 2.4 抄送、扩展字段与通知

#### CC-01 抄送

### CC-01-a 抄送正向：可见只读、通知生成、可标记已读且不阻塞主线

- **需求来源**：PRD §3.3.2（抄送只读知会、不阻塞主线）、§3.5.3、F7.1；TECH §4.2（`blocks_flow=0`）；TEST-PLAN §6.7 CC-01
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（N1 审批人）、`E2E-<runId>-cc`（普通用户，抄送人）、`wangwu`（N2 审批人）。
  - 表单/流程版本与状态：发布表单含 `note`（文本，可见）、`attach`（附件，可见）、`secret_attach`（附件，在抄送节点为 hidden 字段）；发布流程 start → `N1`(lisi) → 抄送节点 `CC`（cc_to=E2E-cc）→ `N2`(wangwu) → end。
  - 实例状态与数据：`RUNNING`，停在 N1，lisi 待办；无抄送任务；`zhangsan` 已上传 `attach` 与 `secret_attach` 各 1 个附件。
- **步骤**：
  1. `lisi` 同意 N1。
  2. 查询 `E2E-cc` 的抄送列表、通知、未读数，以及 `wangwu` 的 N2 待办。
  3. `E2E-cc` 打开详情，尝试处理动作，下载 `attach`，用已知附件 ID 尝试下载 `secret_attach`，再标记抄送已读。
  4. `wangwu` 同意 N2，实例通过。
- **期望结果**：
  1. 页面/接口可观察结果：N1 同意后，抄送任务与 N2 待办同时生成；`E2E-cc` 在“抄送给我”看到记录（非待办/已办），详情只读、无同意/驳回/提交按钮；N2 不等待抄送已读即可生成并处理；实例最终 `APPROVED` 不受抄送是否已读影响；附件区只显示 `attach`，`secret_attach` 的标签与附件不可见，`attach` 可下载，`secret_attach` 下载返回 403/404（R4）。
  2. 数据副作用：抄送不计入主线令牌/进度；抄送任务标记已读仅更新 `is_read/read_at`；不改变实例状态与审批任务；附件下载不改变实例数据。
  3. 通知/审计副作用：`E2E-cc` 收到 1 条抄送通知，未读数 +1；标记已读后未读数 -1；不重复生成抄送任务；时间线显示抄送记录。
- **反例/边界**：
  - 抄送人附件权限按 R4：仅可见字段的附件可下载；hidden 字段及其附件不可见、不可下载。
- **自动化位置**：`testing/e2e/specs/approve.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10（越权码）

### CC-01-b 反向：抄送人不可处理/转办/追加字段，无关人不可见

- **需求来源**：PRD §3.3.2、§2（实例可见性）；PHASE3 §4.6（抄送不参与转办与委托）；TEST-PLAN §6.7 CC-01；TEST-PLAN §6.4 PERM-03
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`E2E-<runId>-cc`（普通用户，抄送人）、`E2E-<runId>-outsider`（无关用户）、`admin`、`lisi`（审批人）、`zhangsan`（发起人）。
  - 表单/流程版本与状态：发布表单含 `attach`（附件，可见）与 `secret_attach`（附件，在抄送节点为 hidden 字段）；发布流程 start → 抄送节点（cc_to=E2E-cc）→ 审批(lisi) → end；实例 `RUNNING`，抄送任务已生成。
  - 实例状态与数据：抄送任务 `is_read=false`；实例存在 1 条审批待办（lisi）；发起人已上传两个附件。
- **步骤**：
  1. `E2E-cc` 对抄送 assignment 调用 `act`，分别尝试 `AGREE`、`REJECT`、`RETURN`、`SUBMIT`。
  2. `E2E-cc` 对抄送 assignment 调用 `transfer`。
  3. `E2E-cc` 调用追加字段接口。
  4. `E2E-cc` 下载 `attach`，用已知附件 ID 尝试下载 `secret_attach`。
  5. `E2E-outsider` 打开实例详情并调用详情/时间线接口。
  6. 查询 `E2E-cc` 的待办/已办与实例状态。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1–3 全部返回结构化 4xx（抄送无处理动作；转办不适用抄送；普通用户无追加字段权限，建议 403）；`E2E-cc` 可下载可见字段附件 `attach`，下载 hidden 字段附件 `secret_attach` 返回 403/404（R4）；`E2E-outsider` 访问详情返回 403/404；`E2E-cc` 只能查看与标记已读。
  2. 数据副作用：实例状态、审批任务、字段数据、抄送任务的 `is_read` 均不变；不产生新任务/动作/通知；附件下载不改变实例数据。
  3. 通知/审计副作用：无新增通知或审计动作。
- **反例/边界**：
  - 抄送人附件权限按 R4：可见字段附件可下载，hidden 字段及其附件不可见、不可下载；本用例只断言“不可处理主线任务、不可转办、不可追加字段、无关人不可见”。
- **自动化位置**：`testing/e2e/specs/permissions.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10

#### EXT-01 运行中追加字段

### EXT-01-a 正向：追加字段仅该实例生效，目标节点可编辑必填，进入快照与归档

- **需求来源**：PRD §3.4 机制 C、F5.1、F5.2；TECH §4.5（L5 扩展字段）、§8 M5；TEST-PLAN §6.7 EXT-01；DEMO §2.6、§2.8
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`admin`（平台管理员）、`zhangsan`（发起人）、`lisi`（N1）、`wangwu`（N2 填写节点）。
  - 表单/流程版本与状态：发布表单含申请区与补充区；发布流程 start → `N1`(lisi) → `N2`(wangwu 填写，开放补充区) → end；同流程另有一个实例 I2。
  - 实例状态与数据：I1 `RUNNING`，停在 N1，lisi 待办；I2 `RUNNING`，停在 N1；I1 尚无扩展字段。
- **步骤**：
  1. `admin` 对 I1 追加字段：`label="合同编号"`、`type=text`、`required=true`、`editable_node_ids=[N2]`、`section_key=补充区`。
  2. 查询 I1 与 I2 的详情/字段权限；`zhangsan`（发起人）查看 I1；`lisi` 查看 I1。
  3. `lisi` 同意 N1；`wangwu` 打开 N2，尝试不填该字段提交，再填写后提交。
  4. 流程到达 `APPROVED` 后，`zhangsan` 查看详情、快照与归档/导出；查询操作审计。
- **期望结果**：
  1. 页面/接口可观察结果：I1 详情出现“合同编号”，N2 节点可编辑且必填；I2 不出现该字段；发起人在运行中不可见该字段，归档后可只读查看（DEMO §2.8）；N1 若可见则为只读、不可编辑（当前节点可见性见 Q18）。
  2. 数据副作用：仅 I1 的实例 schema/数据包含该字段；`wangwu` 不填时提交被拒（422/4xx），任务保持 PENDING；填写后值落库；I2 数据不受影响；停用/删除规则见 EXT-01-b。
  3. 通知/审计副作用：追加行为写入操作审计；该字段进入提交快照与归档数据；若发送追加通知，同一字段对同一接收人恰好 1 条，同名字段再次追加不得被吞掉（TECH M5 通知去重修正；接收人见 Q18）。
- **反例/边界**：
  - 扩展字段控件白名单与通知接收人见 Q18；本用例只使用文本控件。
  - 发起人在运行中不可见、归档可见来自 DEMO §2.8 与 TECH §4.5 查看者维度；若产品确认不同，需回写。
- **自动化位置**：`testing/e2e/specs/dynamic-field.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q18

### EXT-01-b 反向：终态实例、越权用户、非白名单控件与停用边界

- **需求来源**：PRD §3.4 机制 C（终态不可追加、基础控件限制）、F5.1、F5.3；TECH §8 M5（权限校验顺序）；TEST-PLAN §6.7 EXT-01
- **优先级**：P0
- **验证层**：API
- **前置条件**：
  - 角色与组织：`admin`、`zhangsan`（普通用户）、`zhaoliu`（设计者，但非该实例参与者）、`lisi`（参与者）。
  - 表单/流程版本与状态：发布流程 start → 审批 → end；已有 `APPROVED`、`WITHDRAWN`、`TERMINATED` 实例；另有一个 `RUNNING` 实例 I1 已追加字段 `contract_no`。
  - 实例状态与数据：I1 处于 `RUNNING`；终态实例保持终态。
- **步骤**：
  1. `admin` 对 `APPROVED`、`WITHDRAWN`、`TERMINATED` 实例追加字段。
  2. `zhangsan` 对 I1 追加字段。
  3. `zhaoliu`（设计者，非参与者）对 I1 追加字段。
  4. `admin` 用 `subtable` 或 `formula` 类型追加字段。
  5. `admin` 停用 I1 已有的 `contract_no` 字段；再次查询详情与历史数据。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1–4 全部返回结构化 4xx（普通用户/非参与者设计者建议 403；终态与非法类型见 Q10/Q18）；I1/终态实例的 schema、字段值、审计、通知均不变；步骤 5 成功，字段停止编辑/展示，但不可物理删除。
  2. 数据副作用：终态实例不可追加；普通用户与无审批数据管理权的设计者不可追加；非白名单控件不落库；停用后历史值与快照保留（呈现方式见 Q19）。
  3. 通知/审计副作用：失败请求不产生通知/审计；停用行为写操作审计；无重复通知。
- **反例/边界**：
  - “非参与者设计者”的 403 来自 TECH §8 M5 测试说明，并与 PRD §2“设计者无审批数据管理权”对齐；具体口径见 Q18。
  - 停用后归档/导出的值呈现见 Q19。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q18、Q19

### EXT-01-c CSV 导出包含追加字段，公式注入前缀被转义

- **需求来源**：需求方确认规则 R3（2026-11-19）；PRD §3.4 机制 C、F5.2；OpenAPI `GET /instances/{id}/export`
- **优先级**：P0
- **验证层**：API+手工（Excel 打开）
- **前置条件**：
  - 角色与组织：`admin`（平台管理员，具备导出权限）、`zhangsan`（发起人）、`lisi`（审批人）。
  - 表单/流程版本与状态：发布表单，表单模板编码为 `E2E-<runId>-EXP`，含文本字段 `f_eq`、`f_plus`、`f_minus`、`f_at`、`f_normal`，hidden 文本字段 `secret`（审批节点可编辑并已填写），以及 auto_number 字段；发布流程 start → 审批(lisi) → end。
  - 实例状态与数据：实例 `APPROVED`，数据为 `f_eq="=SUM(1,1)"`、`f_plus="+CMD"`、`f_minus="-1+1"`、`f_at="@user"`、`f_normal="正常文本"`、`secret="hidden-value"`；运行中已追加扩展字段 `contract_no`（文本），值为 `HT-001`。
- **步骤**：
  1. `admin` 调用 `GET /instances/{id}/export` 获取 CSV。
  2. 以文本方式检查表头、数据行与导出说明。
  3. 用 Excel/表格软件打开该 CSV，观察单元格显示与公式栏。
- **期望结果**：
  1. 页面/接口可观察结果：CSV 表头含“实例单号”“表单编号”及 `f_eq`、`f_plus`、`f_minus`、`f_at`、`f_normal`、`contract_no`；“实例单号”为 auto_number 值（`E2E` + YYYYMMDD + 4 位流水），“表单编号”为 `E2E-<runId>-EXP`；追加字段列存在且值为 `HT-001`；hidden 字段 `secret` 及其值不出现在导出中。
  2. 数据副作用：`f_eq`、`f_plus`、`f_minus`、`f_at` 四个单元格在 CSV 中分别以 `'=SUM(1,1)`、`'+CMD`、`'-1+1`、`'@user` 存储，`f_normal` 保持“正常文本”不加前缀；导出说明中注明“以 = + - @ 开头的单元格前加单引号，Excel 显示原文本且不执行公式”（R3）；导出为只读操作，不改变实例状态、任务或字段值。
  3. 通知/审计副作用：导出不产生站内通知；实例时间线不新增审批动作。
- **反例/边界**：
  - 仅验证 `=`、`+`、`-`、`@` 四类前缀；值本身已以单引号开头的场景未在 R3 定义，不作为本用例通过条件。
- **自动化位置**：`backend/tests/test_acceptance_execution.py`（建议新建）；Excel 显示效果需手工确认
- **需求待确认项**：无（R3 已确认）

#### NOTIFY-01 消息与角标

### NOTIFY-01-a 正向：新待办、最终结果、抄送通知齐全，角标与跳转正确且 ≤10 秒感知

- **需求来源**：PRD F7.1、F7.2、F4.5；TECH 不变量 #8；TEST-PLAN §6.7 NOTIFY-01
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`（审批人）、`E2E-<runId>-cc`（抄送人）、`wangwu`（审批人）。
  - 表单/流程版本与状态：发布流程 F1：start → N1(lisi) → N2(wangwu) → end；F2：start → N1(lisi) → 抄送(E2E-cc) → end。
  - 实例状态与数据：两个实例均由 `zhangsan` 新建；事件发生前各接收人未读消息清零（可通过新账号或标记已读准备）。
- **步骤**：
  1. `zhangsan` 提交 F1 与 F2；记录提交时间。
  2. 分别在 10 秒内轮询 `lisi`、`wangwu`、`E2E-cc`、`zhangsan` 的 `/notifications/unread-count` 与工作台角标，并打开消息中心。
  3. 点击“新待办”“抄送”通知，检查跳转。
  4. `lisi` 同意 F1；`wangwu` 同意 F1；`lisi` 同意 F2；检查发起人结果通知与抄送通知。
- **期望结果**：
  1. 页面/接口可观察结果：新任务产生后 10 秒内，对应处理人未读数与待办角标更新；通知列表出现可点击记录，点击后跳转到实例详情/对应待办；最终通过后发起人收到结果通知并可跳转；抄送人生成抄送通知，跳转到只读详情。
  2. 数据副作用：通知只影响未读计数，不改变实例/任务；每个事件对每个接收人恰好 1 条通知。
  3. 通知/审计副作用：通知 `is_read` 初始为 false，点击/标记后变 true；已读后未读数递减；不同用户的通知互不可见。
- **反例/边界**：
  - 通知类型枚举、标题文案与“处理结果”粒度见 Q20；本用例按事件语义和实例 `link` 断言，不硬编码未定义类型。
- **自动化位置**：`testing/e2e/specs/notifications.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q20

### NOTIFY-01-b 反向：取消/驳回/终止通知齐全，去重与已读隔离正确

- **需求来源**：PRD F7.1、F4.5、§3.5.3；TECH 不变量 #8（每个事件对每个接收人恰好一条）；TEST-PLAN §6.7 NOTIFY-01
- **优先级**：P0
- **验证层**：API+E2E
- **前置条件**：
  - 角色与组织：`zhangsan`（发起人）、`lisi`、`wangwu`（或签成员）、`admin`、`E2E-<runId>-outsider`（无关用户）。
  - 表单/流程版本与状态：发布或签流程（ANY，lisi、wangwu）与普通审批流程；发布可终止流程。
  - 实例状态与数据：或签实例 `RUNNING`，双方待办；普通实例用于驳回；另一实例用于终止。
- **步骤**：
  1. `lisi` 同意或签；查询 `wangwu` 的通知、待办、未读数。
  2. 普通实例中 `lisi` 驳回；查询发起人通知。
  3. `admin` 终止另一实例；查询发起人与处理人通知。
  4. 对同一驳回动作使用相同 `X-Request-Id` 重放；查询通知总数。
  5. `E2E-outsider` 尝试标记他人的通知已读；`wangwu` 标记自己的通知已读。
  6. 查询新用户（无通知）的消息列表与未读数。
- **期望结果**：
  1. 页面/接口可观察结果：步骤 1 `wangwu` 收到 1 条“无需处理”类知会，待办移除；步骤 2 发起人收到 1 条驳回通知（含意见）；步骤 3 相关人收到终止通知；步骤 4 通知总数不变；步骤 5 越权标记被拒（403/404），本人标记成功且只减自己的未读；步骤 6 返回空列表与 0，不报错。
  2. 数据副作用：通知去重成立，每个事件对每个接收人恰好 1 条；已读状态只影响本人；通知不影响实例状态。
  3. 通知/审计副作用：取消/驳回/终止事件的通知与时间线/审计一致；重放不新增通知。
- **反例/边界**：
  - 被取消任务的通知形式与已办归属见 Q11；通知类型与终止通知范围见 Q16/Q20。
- **自动化位置**：`testing/e2e/specs/notifications.spec.ts`；API 断言建议 `backend/tests/test_acceptance_execution.py`（建议新建）
- **需求待确认项**：Q10、Q11、Q16、Q20

---

## 3. 评审关注点（给产品/业务）

按风险优先，建议先确认以下 5 项，它们会直接改变用例的期望结果：

1. **D-03 已确认**：并行组成员退回取消整组并重派；PRD §3.5.3 的相反表述需回写。
2. **D-01 已确认部门主管口径**；Q6/Q7 的多管理员兜底与剔除后为空按 `P0-DECISIONS.md` §4 默认执行。
3. **Q3 提交幂等语义**：重复提交应返回同一结果还是 409，影响所有幂等类断言与前端重试逻辑。
4. **Q10/Q23 非法动作错误码与伪造字段处理**：整单拒绝还是静默过滤，决定反向用例的断言口径与用户提示。
5. **Q11/Q20 取消/知会与通知类型**：被取消任务是否进“已办”、通知类型与“处理结果”粒度，影响工作台与消息中心验收。

其余 Q 项可在执行首轮用例时逐条确认并回写本文件。
