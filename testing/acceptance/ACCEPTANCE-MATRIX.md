# 验收矩阵（需求 → 用例 → 结果）

> 本文件是 G1 验收的**唯一汇总口径**。`bash scripts/check.sh` 全绿、代码覆盖率、单元测试数量都不能替代这里。
>
> 用例设计规则见 `testing/acceptance/README.md`；场景基线见 `testing/plan/TEST-PLAN.md` §6。
> 最近更新：2026-11-19（G1 API R1 执行完成：17/20，通过 2 个缺陷）

## 0. 汇总

| 指标 | 数值 |
|---|---|
| P0 场景 | 44 |
| P1 场景 | 4 |
| 已设计用例 | 132 条 + 38 项非功能检查 |
| 已自动化 | 45 条（G1 API R1–R7） |
| 最近一次执行通过率 | 45/45（100%） |
| 未关闭 S1 / S2 | 0 / 0（BUG-API-001..009 已修） |
| 待确认产品决策 | 0（D-01–D-04 已确认；D-05 默认执行） |

### 0.1 用例文件

| 文件 | 覆盖 | 数量 |
|---|---|---|
| `P0-CASES-01-DESIGN-PERM.md` | AUTH / ORG / FORM / FLOW / PERM | 40 条 |
| `P0-CASES-02-EXECUTION-EXCEPTION.md` | INIT / TASK / 驳回退回撤回终止 / CC / EXT / NOTIFY | 49 条 |
| `P0-CASES-03-SEARCH-SEC-NFR.md` | SEARCH / ARCHIVE / DASH / SEC / CONC + ENV/PERF/UAT | 43 条 + 38 项检查 |
| `P0-DECISIONS.md` | 已确认决策、实现默认、文档冲突 | — |

状态定义：

- `TODO`：未设计
- `DESIGNED`：用例已写，待执行
- `PARTIAL`：部分子用例已执行，尚未覆盖整个场景
- `AUTOMATED`：已进入 API/E2E 套件
- `PASS` / `FAIL`：最近一次执行结果
- `BLOCKED`：环境或依赖阻塞
- `N/A`：不适用或已由新用例替代

---

## 1. 认证、组织与派单

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| AUTH-01 | P0 | PRD F6.4；TECH §5.2 | 登录/登出/改密/停用；旧 token 立即失效；错误提示不泄露账号存在性 | API+E2E | `testing/api/test_auth.py` | PASS | R4: 登录/登出/改密/停用/重置密码 PASS | — |
| ORG-01 | P0 | PRD F6.2；PRD §3.3.2 | 部门树、主管、角色成员维护；主管/角色派单解析正确 | API+E2E | `testing/api/test_org.py` | PARTIAL | R2: 向上查找/无主管兜底 PASS；角色成员变更/CRUD 待执行 | — |
| ORG-02 | P0 | PRD F6.2；R1 / D-01 | 已派任务保持原处理人；后续节点按最新组织解析，主管人可向上查找 | API+E2E | `testing/api/test_custom_flows.py` | PARTIAL | R6: 运行中换主管、已派不变、后续按新主管 PASS；部门移动/角色变更待执行 | — |

## 2. 表单设计与版本

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| FORM-01 | P0 | PRD F1.2–F1.7 | 全控件表单设计→发布→发起页渲染；子表/公式/级联/附件/人员正确 | API+E2E | 待建 | DESIGNED | — | — |
| FORM-02 | P0 | PRD F1.5；F2.6 | 旧实例锁旧版；新流程锁最新已发布版；草稿不影响线上 | API+E2E | 待建 | DESIGNED | — | — |
| FORM-03 | P0 | PRD F3.2；§7 安全 | 绕过前端直接调 API：hidden/必填/值规则仍被服务端拦截 | API | 待建 | DESIGNED | — | — |
| FORM-04 | P0 | PRD F1.4；F2.3；PHASE2 M8/M9 | 布局/展示控件/联动规则在发起与审批视角的显隐/只读/必填正确 | E2E | 待建 | DESIGNED | — | — |

## 3. 流程设计与发布

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| FLOW-01 | P0 | PRD F2.1–F2.4；§3.3 | 顺序/条件/嵌套/并行/会签/或签/填写/抄送/结束全部可配置、可发布、可运行 | API+E2E | 待建 | DESIGNED | — | — |
| FLOW-02 | P0 | PRD F2.7 | 孤儿节点、无审批人、引用不存在字段、空分支等不可发布，错误可定位 | API | 待建 | DESIGNED | — | — |
| FLOW-03 | P0 | PRD F2.7；§7 | 深嵌套/100 节点/重名/删除被引用字段：行为明确，不产生 500 | API+手工 | 待建 | DESIGNED | — | — |

## 4. 权限与可见性

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| PERM-01 | P0 | PRD F2.3；§3.4 | 节点×字段 hidden/readonly/editable/required 正确；分区批量+单字段覆盖 | API+E2E | 待建 | DESIGNED | — | — |
| PERM-02 | P0 | PRD §3.4；§7 安全；D-04 | hidden 字段不出现在响应/快照/导出/打印；伪造提交值被过滤 | API+E2E | `testing/api/test_snapshots.py` | PARTIAL | R7: hidden key/值、导出、快照/对照 PASS；打印/附件待执行 | BUG-API-001/004/008（已修） |
| PERM-03 | P0 | PRD §2；§7；F6 | 参与者/管理员/设计者/无关人员四视角正确；越权 ID 返回 403/404 | API+E2E | `testing/api/test_permissions.py` | PARTIAL | R2: 无关人/设计者实例访问 PASS；快照/导出/任务 IDOR 待执行 | — |
| PERM-04 | P0 | PRD F3.2/F4.4；TECH M6 决策 | 附件下载权限：上传者/管理员/实例参与者；临时附件正确绑定 | API+E2E | `testing/api/test_attachments.py` | PARTIAL | R8: 临时/提交绑定/参与者/无关人/非法扩展名 PASS；hidden 附件字段/打印待执行 | BUG-API-009（已修） |
| SEC-01 | P0 | PRD §7 安全 | IDOR：实例/任务/附件/模板/审计/导出接口逐一用无关用户访问 | API | 待建 | DESIGNED | — | — |
| SEC-02 | P0 | PRD §7 安全；PHASE2 M10 | 富文本 XSS、CSV 注入、上传白名单/大小/路径穿越 | API+手工 | 待建 | DESIGNED | — | — |

## 5. 发起与提交

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| INIT-01 | P0 | PRD F2.5；F3.1 | 发起范围（全员/角色/部门）正确；无权限看不到入口，直接访问也被拒 | API+E2E | 待建 | DESIGNED | — | — |
| INIT-02 | P0 | PRD F3.2；F3.3；D-04 | 自动填充、标题字段、隐藏字段、只读字段、草稿保存/恢复正确 | API+E2E | `testing/api/test_initiate.py` | PARTIAL | R3: 发起页/草稿/提交 PASS；hidden schema 裁剪 PASS；其余待执行 | BUG-API-001（已修） |
| INIT-03 | P0 | PRD F3.4；§7 一致性 | 连点/刷新/网络重试只产生一个实例和一套任务 | API+E2E | `testing/api/test_initiate.py` | PARTIAL | R2: 单会话重复提交 PASS；双会话并发待执行 | — |
| INIT-04 | P0 | PRD F3.5；§3.3.2 | 表单人员/部门主管/指定部门/角色/发起人自审规则正确 | API+E2E | 待建 | DESIGNED | — | — |

## 6. 审批处理与流程状态

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| TASK-01 | P0 | PRD F4.1 | 待办/已办/我发起/抄送内容、计数、分页、筛选正确；会签组合并展示 | API+E2E | `testing/api/test_tasks.py` | PARTIAL | R2: done/mine 验证；筛选/分页/合并待执行 | — |
| TASK-02 | P0 | PRD F4.2/F4.3；§3.5.4 | 同意/驳回/退回/撤回/终止在合法与非法状态下的守卫、提示、通知 | API+E2E | `testing/api/test_tasks.py` | PARTIAL | R4: 同意/驳回/撤回/终止守卫 PASS；退回/通知待执行 | — |
| TASK-03 | P0 | PRD §3.5.3；F4.3 | 会签 all/any：同时待办、分别操作、一人驳回、或签后取消其余 | API+E2E | `testing/api/test_custom_flows.py` | PARTIAL | R6: 会签 all 正向、或签 any 取消其余 PASS；组内驳回待执行 | — |
| TASK-04 | P0 | PRD §3.5.3；D-03 | 并行组 all/any 汇合正确；不提前推进、不永久卡住；退回取消整组并重派 | API+E2E | `testing/api/test_custom_flows.py` | PARTIAL | R6: all/any 汇合、并行组退回整组重派 PASS；提前推进/卡死边界待执行 | — |
| TASK-05 | P0 | PRD F4.3/F4.4/F4.6 | 处理意见/附件/字段修改：必填可配、diff 留痕、附件权限正确 | API+E2E | 待建 | DESIGNED | — | — |
| TASK-06 | P0 | PRD F4.3；§7 | 同一任务两人同时处理、同一人双击、多标签页：结果唯一且可解释 | API+E2E | `testing/api/test_tasks.py` | PARTIAL | R2: 重复提交/重复处理 PASS；双会话并发待执行 | — |
| TASK-07 | P0 | PHASE3 M14 §4 | 转办/委托：派单、可见性、留痕、窗口边界/重叠/撤销正确 | API+E2E | `testing/api/test_delegation.py` | PARTIAL | R5: 转办推进、委托派单/委托人可见、自委托/重叠拒绝 PASS；通知/时间线/会签组转办待执行 | BUG-API-006/007（已修） |

## 7. 驳回、退回与异常路径

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| REJECT-01 | P0 | PRD F3.6；§3.5.4 | 驳回→发起人；轮次+1；意见/快照可查；仅可编辑字段可改；重走全流程 | API+E2E | `testing/api/test_lifecycle.py` | PARTIAL | R4: 驳回→REJECTED、重提轮次+1、重走 PASS；快照/diff 待执行 | — |
| RETURN-01 | P0 | PRD §3.5.4；F4.3；D-03 | 退回指定前序节点：数据不回滚；前序不重走；目标节点收到任务 | API+E2E | `testing/api/test_custom_flows.py` | PARTIAL | R6: 并行组退回取消整组、目标重派 PASS；顺序退回/非法目标待执行 | — |
| WITHDRAW-01 | P0 | PRD §3.5.4 | 已被处理不可撤回；撤回后任务取消、通知正确 | API+E2E | `testing/api/test_lifecycle.py` | PARTIAL | R4: 无人处理可撤回、任务取消、旧任务拒绝 PASS；已处理后撤回/通知待执行 | — |
| TERMINATE-01 | P0 | PRD §3.5.4 | 有权限者才能终止；终止后不可处理；相关人收到通知 | API+E2E | `testing/api/test_lifecycle.py` | PARTIAL | R4: 管理员终止、任务取消、非管理员拒绝 PASS；通知/时间线待执行 | — |
| CC-01 | P0 | PRD F4.1/F7.1；§3.5.2 | 抄送可见不可操作；通知生成；不阻塞主线 | API+E2E | `testing/api/test_lifecycle.py` | PARTIAL | R4: 抄送可读/标记已读、不可处理 PASS；附件/隐藏字段待执行 | — |
| EXT-01 | P0 | PRD F5.1–F5.4 | 运行中追加字段：仅该实例生效；权限/必填/停用正确；进快照/归档 | API+E2E | 待建 | DESIGNED | — | — |
| NOTIFY-01 | P0 | PRD F7.1/F7.2 | 新待办/结果/抄送/取消/驳回通知齐全；已读/跳转正确；≤10s 感知 | API+E2E | 待建 | DESIGNED | — | — |

## 8. 检索、归档与首页

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| SEARCH-01 | P0 | PHASE3 M13 §3；PRD F8.1；D-05 | 文本包含/等于、数字范围、日期、选项操作符正确；表单编号与实例单号不混用 | API+E2E | `testing/api/test_search.py` | PARTIAL | R9: text contains/eq、number between/gte、AND、mine/all 权限 PASS；日期/人员/多选/编号语义待执行 | — |
| SEARCH-02 | P0 | PHASE3 M13 §3；SEARCH-FILTER-PLAN | 新增/修改后可检索；重建索引与在线数据一致；权限范围正确 | API | `testing/api/test_search.py` | PARTIAL | R9: 配置+提交后索引可检索 PASS；重建脚本/配置删除/跨版本待执行 | — |
| ARCHIVE-01 | P0 | PRD F8.1；M6；D-05 | 归档只含已通过；CSV 列完整（含动态字段）、中文不乱码；非管理员不可导出 | API+E2E | `testing/api/test_archive.py` | PARTIAL | R5: 仅 APPROVED、批量/单实例导出、BOM/转义 PASS；列序/动态字段待执行 | BUG-API-003/004/005（已修） |
| DASH-01 | P0 | PHASE3 M11 §1；D-02 | 普通用户/设计者个人工作台；管理员额外概览；空状态不报错 | API+E2E | `testing/api/test_permissions.py` | PARTIAL | R3: 设计者 admin=null PASS；其余角色/口径待执行 | BUG-API-002（已修） |

## 9. 并发、环境与性能

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| CONC-01 | P0 | PRD §7 一致性 | 会签同时操作、撤回/同意、终止/同意、转办/自动派单并发时结果可解释 | API | `testing/api/test_concurrency.py` | PARTIAL | R8: 并发会签同时同意 PASS；撤回/终止/或签并发待执行 | — |
| ENV-01 | P0 | PRD §7 部署；README Docker | Docker MySQL 8 / PostgreSQL 16 全新部署可启动；重启持久化；附件卷 | 手工脚本 | 待建 | DESIGNED | — | — |
| ENV-02 | P0 | PRD §7；TECH §3.1 | 空库迁移、上一版本升级迁移成功；SQLite/MySQL/PG 核心链路一致 | 手工脚本 | 待建 | DESIGNED | — | — |
| ENV-03 | P0 | TECH §9 时间统一；PRD §7 | UTC 存储与 Asia/Shanghai 展示边界；首页今日/本周/本月跨日正确 | API+手工 | 待建 | DESIGNED | — | — |
| PERF-01 | P0 | PRD §7 规模；TEST-PLAN §10.3 | 1k/10k 实例列表与筛选、100 节点设计器、待办/首页达到基线 | 脚本 | 待建 | DESIGNED | — | — |
| UAT-01 | P0 | TEST-PLAN §13.2 | 产品负责人独立走完：配置新流程、发起审批、驳回重提、检索导出 | 手工 | — | DESIGNED | — | — |

## 10. P1 模块（试用期内覆盖）

| 用例 ID | 优先级 | 需求来源 | 验收点 | 验证层 | 自动化位置 | 状态 | 最近结果 | 缺陷 |
|---|---|---|---|---|---|---|---|---|
| SHEET-01 | P1 | PHASE3 M12 §2 | 共享表格：创建/编辑/自动保存/冲突/导出/权限 | API+E2E | 待建 | TODO | — | — |
| AI-01 | P1 | PHASE3 M15 §5 | 默认关闭；生成→校验→预览→应用；不自动发布；限流/审计/失败重试 | API+E2E | 待建 | TODO | — | — |
| PRINT-01 | P1 | PHASE2 M10 §4 | A4 打印：分页/字段/时间线/hidden 字段正确 | 手工 | — | TODO | — | — |
| MOBILE-01 | P1 | PHASE2 M10 §4 | 390px 核心路径可用，无横向溢出 | E2E+手工 | 待建 | TODO | — | — |

---

## 11. 需求决策与待确认清单

| # | 问题 | 结论 | 依据 / 影响用例 |
|---|---|---|---|
| 1 | 运行中修改部门/角色/主管，已派任务与后续节点按哪个时点解析？ | 已派任务保持原处理人不变；后续进入新节点时按当时最新组织解析派单 | 产品负责人 2026-11-19；ORG-02、INIT-04 |
| 2 | 撤回与终止的角色/状态，以及通知接收人？ | 撤回：仅发起人，且尚无任何任务被处理过；终止：仅平台管理员，任意非终态；通知受影响处理人与发起人（按 F7.1） | PRD §3.5.4、F7.1；WITHDRAW-01、TERMINATE-01 |
| 3 | 抄送人能否下载附件、能否看到 hidden 字段？ | 跟随字段权限：可见字段只读、附件可下载；hidden 字段及其附件不可见 | 产品负责人 2026-11-19；CC-01、PERM-02/04 |
| 4 | 导出 CSV 对 `= + - @` 开头单元格的处理策略？ | 单元格前加单引号 `'`，Excel 显示原文本且不执行公式；导出说明中注明 | 产品负责人 2026-11-19；SEC-02、ARCHIVE-01 |
| 5 | "表单编号"与"实例单号"的生成规则、唯一性与展示口径？ | 表单编号 = 表单模板编码；实例单号 = 表单内 `auto_number` 字段值（标识位 + YYYYMMDD + 当日流水）；列表和筛选按此区分 | 产品负责人 2026-11-19；TECH §3.3；SEARCH-01、ARCHIVE-01 |
| 6 | 委托期内原处理人是否仍保留查看权/处理权？ | 保留实例查看权，不再处理；委托只影响新派发任务，已有待办需逐条转办 | PHASE3 M14 §4.2/§4.4；TASK-07、PERM-03 |

---

## 12. 执行记录

| 轮次 | 日期 | 范围 | 执行人 | 通过/总数 | 报告 |
|---|---|---|---|---|---|
| R0 | 2026-11-19 | E2E 工程冒烟（登录/菜单/种子数据，非验收结论） | Claude | 6/6 | `testing/.runtime/playwright-report/` |
| R1 | 2026-11-19 | P0 用例设计（Spec-only，三份草案） | Claude + 需求方确认 | 132 条 / 44 场景 | `P0-CASES-*.md`、`P0-DECISIONS.md` |
| R2 | 2026-11-19 | P0 G1 API 黑盒第一批（AUTH/ORG/INIT/TASK/PERM） | Claude | 17/20（2 缺陷） | `testing/reports/2026-11-19-p0-api-r1.md` |
| R3 | 2026-11-19 | 修复 BUG-API-001/002 后复跑（API + E2E + 全量 check） | Claude | 20/20 API；6/6 E2E；452 pytest + 128 vitest 全绿 | `testing/reports/2026-11-19-p0-api-r1.md` |
| R4 | 2026-11-19 | P0 G1 API 第二批（AUTH/REJECT/WITHDRAW/TERMINATE/CC/ARCHIVE/导出） | Claude | 30/30（BUG-API-003/004/005 已修） | `testing/reports/2026-11-19-p0-api-r2.md` |
| R5 | 2026-11-19 | P0 G1 API 第三批（转办/委托/归档批量导出） | Claude | 34/34（BUG-API-006/007 已修） | `testing/reports/2026-11-19-p0-api-r3.md` |
| R6 | 2026-11-19 | P0 G1 API 第四批（自建流程：ORG-02/或签/并行退回） | Claude | 37/37（无新缺陷） | `testing/reports/2026-11-19-p0-api-r4.md` |
| R7 | 2026-11-19 | P0 G1 API 第五批（快照/快照对照 hidden 裁剪） | Claude | 38/38（BUG-API-008 已修） | `testing/reports/2026-11-19-p0-api-r5.md` |
| R8 | 2026-11-19 | P0 G1 API 第六批（附件权限/并发会签） | Claude | 42/42（BUG-API-009 已修） | `testing/reports/2026-11-19-p0-api-r6.md` |
| R9 | 2026-11-19 | P0 G1 API 第七批（SEARCH 业务字段筛选） | Claude | 45/45（无新缺陷） | `testing/reports/2026-11-19-p0-api-r7.md` |

## 13. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-11-19 | 初始化 P0/P1 场景矩阵；登记 6 条需求待确认项 |
| 2026-11-19 | 确认组织变更、编号语义、CSV 注入、抄送附件 4 条规则；引用 PRD/PHASE3 关闭撤回/终止与委托 2 条 |
| 2026-11-19 | 三份 P0 草案完成（132 条 + 38 检查）；确认 D-01–D-04；矩阵状态更新为 DESIGNED |
| 2026-11-19 | G1 API R1 执行 20 条：17 通过、3 失败；登记 BUG-API-001（hidden key 泄露）、BUG-API-002（设计者概览） |
| 2026-11-19 | 修复 BUG-API-001/002；API 复跑 20/20、E2E 6/6、受影响后端单测 97 passed |
| 2026-11-19 | 全量 `check.sh` 五项全绿（452 pytest + 128 vitest + ruff/vue-tsc/build） |
| 2026-11-19 | G1 API R2：30/30；修复 BUG-API-003（归档状态）、004（导出 hidden 列）、005（CSV 注入）；全量 check 全绿 |
| 2026-11-19 | G1 API R3：34/34；修复 BUG-API-006（转办卡死，S1）、007（origin 可见性）；全量 check 全绿 |
| 2026-11-19 | G1 API R4：37/37；自建流程覆盖 ORG-02、或签 any、并行退回 D-03；无新缺陷 |
| 2026-11-19 | G1 API R5：38/38；修复 BUG-API-008（运行中快照/对照泄露 hidden 字段） |
| 2026-11-19 | G1 API R6：42/42；修复 BUG-API-009（提交携带附件未绑定实例）；并发会签通过 |
| 2026-11-19 | G1 API R7：45/45；SEARCH 文本/数字/AND/权限与错误分支通过；无新缺陷 |
