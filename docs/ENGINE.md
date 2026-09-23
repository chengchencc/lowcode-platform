# FlowForm 引擎说明

> **给谁看**：第一次读 `backend/app/engine/` 的人（含 Spring / Java 背景的同事）。
> **配套**：语义契约（每个事件该做什么）在 `docs/TECH-DESIGN.md` §4，领域规则在
> `PRD-lowcode-form-approval.md` §3.4 / §3.5。本文只回答三件事：
> **代码分几块、一次请求经过哪里、改一处该跑哪个测试**。

---

## 1. 双层模型（一句话版本）

```
顶层：实例生命周期状态机（用户可感知）   DRAFT → RUNNING → APPROVED / REJECTED / WITHDRAWN / TERMINATED
底层：节点执行器 + 并行令牌（Token）      每个待办任务 = 一个活跃令牌，各自独立推进
```

顶层状态**不是**独立维护的，而是令牌集合的投影 —— `_sync_current_nodes()` 把
「还挂着的阻塞令牌」写成实例上的冗余列供列表页展示。这也是为什么退回不改变顶层状态：
它只换令牌，实例仍 RUNNING（PRD §3.5.4）。

| 概念 | 落地 |
|---|---|
| 活跃令牌 | `tasks` 行，`status='PENDING' AND blocks_flow=1` |
| 令牌位置 | `(node_key, gates, round)` 三元组 |
| 会签 all / 或签 any | 1 个 `tasks` 行 + N 个 `task_assignments`（`assignee_mode`） |
| 依次审批 | 同上，`seq` 升序，仅最小 seq 为 PENDING |
| 并行组成员 | 同 `group_id` 的多个 `tasks` 行 |
| 抄送知会 | `tasks.node_type='CC'`，`blocks_flow=0` —— 不占令牌、不计进度、主线不等它 |

`gates` 是分支决策链（如 `["s2:s2a"]`），是判断「令牌在不在 target 的祖先链上」的唯一
依据。退回的取消范围因此能写成纯函数。

---

## 2. 模块地图

17 个文件分三层。**分层不是审美问题**：只有不碰数据库的那一层，才能把会签/或签/
退回取消范围这类语义穷举测试（120 项纯核心单测不碰数据库，秒级跑完；同样这批用例
一旦需要起库，本机就是分钟级）。

### 2.1 数据结构与契约

| 模块 | 内容 | 说明 |
|---|---|---|
| `types.py` | `Cursor` / `Placement` / `NodeDef` / `CompiledFlow` / `TokenOp` / `EngineEvent` / `EngineResult` / `AssignmentView` / `TaskView` / `NotificationDraft` / `ActionContext` | 全是 dataclass / 枚举，不带 ORM。纯核心之间用它通信 |
| `errors.py` | `EngineError` · `FlowInvalid` · `IllegalTransition`（另有 `TokenConflict` / `PermissionDenied` / `ApproverUnresolved` / `ExpressionError` 四个**目前没有调用点**） | 表示**定义或引擎状态**有问题。用户层面的错误（「有人处理过之后不能撤回」）走 `app/core/errors.py` 的业务异常 |

### 2.2 纯核心（不得 import `db` / `models`）

| 模块 | 关键函数 | 职责 |
|---|---|---|
| `compile.py` | `compile_flow` · `compile_definition` · `parse_flow_definition` | 树形定义（steps / branches / members）→ 有序列表 + `Placement`；校验 id 全局唯一与结构约束。**编译一次，运行期只查表** |
| `conditions.py` | `evaluate_condition` · `evaluate_group` · `pick_branch` | 条件表达式求值。字段缺失一律视为「不匹配」，绝不抛错 |
| `expressions.py` | `evaluate_formula` · `evaluate_schema_formulas` | 公式：四则 / 子表合计 / 日期差 / 拼接。手写词法 + 递归下降，**刻意不用 `eval`**；运算符语义由公式类型决定 |
| `machine.py` | `can_transition` · `next_status` · `assert_transition` · `is_terminal` · `is_editable` | 顶层状态机的合法迁移表（非法迁移必须报错，不能静默通过） |
| `router.py` | `plan_start` · `plan_after_node` · `plan_after_group` · `allowed_return_targets` · `cancel_set_for_return` | 令牌推进与取消范围。条件节点与并行组在这里被**展开**（条件节点自身不产生令牌） |
| `aggregate.py` | `node_state` · `group_state` · `next_sequential_seq` · `normalize_mode` · `should_cancel_siblings_on_pass` | 会签 / 或签 / 依次的达成判定（节点内 vs 并行组，刻意分两个函数） |
| `approvers.py` | `ApproverProvider`（Protocol）· `resolve_approvers` · `resolve_cc` · `order_by_mode` | 审批人解析。**这里不查库**，查询通过协议注入（实现放 services 层）；解析结果快照进任务，组织调整不影响已生成的任务 |
| `permissions.py` | `resolve_field_permissions`（L0–L5）· `resolve_view_permissions` · `column_ref` · `apply_ext_fields` | 字段权限矩阵求值，返回值带 `reason` 供前端提示 |
| `fields.py` | `apply_field_patch` · `FieldDiff` · `field_label_index` | 字段写入：**只收当前节点可编辑的键**（其余静默忽略，保证幂等重放安全）；**公式由服务端重算覆盖** |
| `validate.py` | `validate_flow_definition` · `ValidationIssue` | 流程定义校验，面向设计器：先调 `compile`，再叠业务规则，问题**一次性收齐返回** |
| `value_rules.py` | `validate_values` | 字段值校验，面向填写者：只查「本次由这个人负责的字段」，与前端 `formValue.ts` 一一对应 |
| `snapshot.py` | `build_snapshot_payload` · `hash_values` · `diff_snapshots` | 快照只存 `{values, ext_fields}`，**不复制模板 schema**（`form_versions.schema` 不可变，够还原） |
| `notify.py` | `task_created` · `task_cancelled` · `instance_status_changed` · `cc_received` · `returned` · `ext_field_added` · `abnormal_assignment` | 只产出通知**草稿**，落库由 service 做。每条带 `dedup_key`，靠唯一索引兜住事务重放 |
| `ext_fields.py` | `normalize_spec` · `merge_ext_fields` · `make_field_key` | 机制 C：运行中追加字段的校验与 schema 合并（合并后前端不必区分模板字段与扩展字段） |

### 2.3 编排层（唯一允许 import `models` 的模块）

| 模块 | 职责 |
|---|---|
| `service.py` | `EngineService` —— 引擎**唯一**写入口。事务骨架、全部落库、审计与通知的生成时机都在这里 |

> **分层约束的执行现状**：TECH-DESIGN §2 写的是「M3 起用 import-linter 在 CI 校验」，
> 实际至今**没有接**（仓库里既无 import-linter 依赖也无 CI 配置）。当前事实上的关卡只有一个：
> **`service.py` 是 `engine/` 里唯一 import `app.models` 的文件**，`ruff` 也没有相关规则。
> 也就是说这条线靠约定与评审守着 —— 改动时请别把 `Session` 带进纯核心，
> 一旦带进去，120 项纯核心单测会立刻需要起库。

---

## 3. 一次提交（SUBMIT）的完整链路

以 `EngineService.submit()` 为例，其余公开事件（同意/驳回/退回/撤回/终止…）骨架相同：
**锁实例 → 状态机 guard → 校验 → 计算令牌操作 → 落库 → 写 action / snapshot → 通知 → 提交**。

```
submit()                                             service.py
  ├─ _lock(instance.id)                    ← 所有事件的第 0 步：锁实例行
  │                                          （MySQL 发 SELECT ... FOR UPDATE；SQLite 忽略它，单写者已串行）
  ├─ instance.status == DRAFT ?            ← 否则 IllegalTransition
  └─ _start_round()                        ← 提交与重提的公共部分
       ├─ _schema_for / _compiled()        ← 定义 → CompiledFlow（运行期查表用）
       ├─ _permissions_for(start 节点)      ← 字段权限 L0–L5（含机制 C 的 L5）
       ├─ apply_field_patch(current, patch, permissions, form_schema)
       │       → values, diffs             ← 只接受可编辑键；公式在这里被重算覆盖
       ├─ _assert_required(全量)           ← 提交是整单提交，必填全查
       ├─ _assert_values_valid(只查本次可编辑的)   ← 谁填的值谁负责
       ├─ assert_transition(DRAFT → RUNNING)
       ├─ _write_action()                  ← 审计留痕（含 changed_fields diff）
       ├─ _write_snapshot(SUBMIT)          ← ★ 必须在派发之前：seq 要与时间顺序一致
       ├─ plan_start(compiled, values) → [Cursor, ...]
       ├─ _dispatch()                      ← 把一批 Cursor 变成任务
       │    ├─ 命中 end   → _finish() → APPROVED + 归档快照 + 通知全体参与人（不建任务行）
       │    ├─ 命中 cc    → resolve_cc + 抄送任务，然后递归继续主线（不阻塞）
       │    └─ 其余节点    → _spawn()：Tasks(+ group_id / activation_seq / blocks_flow)
       │                              + TaskAssignments(assignee_mode / seq)
       └─ _sync_current_nodes()            ← 顶层状态投影（列表页展示用）
  ├─ _persist_notifications(dedup_key)     ← 唯一索引兜住事务重放
  └─ db.commit()
```

**三条顺序约定**（都有测试兜着，改顺序会红）：

1. **快照在派发之前写** —— 否则快照 seq 与时间顺序颠倒。
2. **值校验在写 action 之前** —— 校验失败不该留下一条审计。
3. **抄送派发后主线立即继续** —— 抄送不占令牌，主线不等它。

顺带两个位置概念：

| 字段 | 含义 |
|---|---|
| `round` | 「驳回后重提」的轮次，重提时 +1，历史任务保留 |
| `activation_seq` | 「同一节点第几次被激活」。退回重派时 +1 —— 这就是「已通过的更早节点不重走、但被退回节点要重派」的落地方式 |

### 一次「同意」走到哪

```
act()  → _handle_pass()
  ├─ node_state(mode, assignments)          ← OPEN / DONE / FAILED
  │    ├─ OPEN  且是依次审批 → 激活下一个 seq，本次结束（顶层状态不变）
  │    └─ DONE  → 本任务 COMPLETED
  │          ├─ 或签：取消其余 assignments（理由 ANY_SIGN_DONE）
  │          ├─ 在并行组里 → group_state(members)
  │          │      ├─ OPEN   → 停在组前，等其余成员
  │          │      ├─ JOINED → plan_after_group()（或签还要作废其余成员）→ _dispatch()
  │          │      └─ FAILED → _fail_group()
  │          └─ 不在组里 → plan_after_node() → _dispatch()（命中 end 即 APPROVED）
  └─ _dispatch 里再 _sync_current_nodes()

act()  → _handle_return()   ← 退回
  ├─ cancel_set_for_return()  取消 target 之后的全部令牌（纯函数，见 router.py）
  └─ 在 target 上 activation_seq+1 重派    ← 顶层状态保持 RUNNING，current_data 不回滚
```

---

## 4. 改一处代码 → 跑哪个测试

测试入口统一走脚本（`bash` 已随 Git for Windows 进 PATH）：

```bash
bash scripts/check.sh backend tests/test_engine_core.py            # 单文件（自动 -n0）
bash scripts/check.sh backend tests/test_engine_core.py::TestRouter # 单个测试类
bash scripts/check.sh quick                                        # ruff + vue-tsc + vitest
bash scripts/check.sh                                              # 全量五项，约 4 分钟
```

| 想改什么 | 先读 | 跑 |
|---|---|---|
| 分支走向 / 条件求值 | `conditions.py` · `router.py` | `tests/test_engine_core.py::TestRouter`、`::TestConditions` |
| 会签 / 或签 / 依次审批 | `aggregate.py` | `::TestAggregate` |
| 退回的取消范围 | `router.cancel_set_for_return` | `::TestReturn` + `tests/test_engine_service.py::TestReturn` |
| 字段权限矩阵 L0–L5 | `permissions.py` | `::TestPermissions` + `tests/test_engine_service.py::TestFieldPermissions` |
| 公式语义 | `expressions.py` | `tests/test_engine_expressions.py`（+ 前端 `formula.spec.ts`，共用 `docs/formula-test-vectors.json`） |
| 字段值规则 | `value_rules.py` | `tests/test_value_rules.py`（+ 前端 `formValue` 测试） |
| 审批人解析 / 兜底 | `approvers.py` | `tests/test_engine_service.py::TestApproverResolution` |
| 机制 C 追加字段 | `ext_fields.py` | `::TestExtFields`（`test_engine_core.py` 纯函数 + `test_engine_service.py` 全链路） |
| 状态机迁移合法性 | `machine.py` | `::TestMachine` |
| 通知内容 / 去重键 | `notify.py` | `tests/test_engine_service.py::TestIdempotency`（断言落在 `notifications.dedup_key` 上） |
| 快照与对照 | `snapshot.py` | `tests/test_reimburse_scenario.py`（快照对照走 HTTP，见文件内 `snapshots/diff` 用例） |
| 事务编排本身 | `service.py` | `tests/test_engine_service.py` 全量 + `tests/test_reimburse_scenario.py`（只走 HTTP 的端到端） |

> **注意 TECH-DESIGN §8 的那张 M3 单测清单已经过时**：它列的 `test_compile.py` /
> `test_conditions.py` / `test_machine.py` / `test_router.py` / `test_permissions.py` /
> `test_aggregate.py` 六个文件**并不存在** —— 落地时合并成了 `tests/test_engine_core.py`
> 里的 `TestCompile` / `TestConditions` / `TestMachine` / `TestRouter` / `TestReturn` /
> `TestAggregate` / `TestPermissions` / `TestExtFields` 八个测试类（共 120 项，不碰数据库）。
> 以本文的表为准。

---

## 5. 引擎这一层的坑

语义层面的坑（`autoflush`、或签成员取消、快照时机等 6 条 M3 修过的真 bug）在
TECH-DESIGN §8「M3 实现中修掉的真 bug」，通用陷阱在 §9。这里只列读代码时最容易踩的：

1. **`service.py` 内部依赖 `flush` 时机** —— 会话是 `autoflush=False`，
   写完任务/分配后若不 `flush`，紧接着的聚合查询读不到本事务的改动，会把 OPEN 误判成别的状态。
   `_active_node_keys` 开头就显式 `flush()` 正是为此。
2. **聚合模式有两套词汇表** —— 流程定义里是 `"any"` / `"all"`，枚举是 `ANY` / `ALL`。
   `aggregate.normalize_mode()` 是**唯一**归一化点，别在别处直接比字符串（M3 因此静默走错过分支）。
3. **`activation_seq` 不是 `round`** —— 想区分「同一节点的第二次激活」用前者，
   想区分「驳回后的新一轮」用后者。退回重派只动前者。
4. **字段写入是「静默忽略」而非报错** —— 不可编辑的键会被 `apply_field_patch` 丢掉。
   排查「前端明明传了值却没存上」时，先看权限矩阵，而不是先怀疑 DTO。
5. **`instance_actions.task_id = 0` 表示实例级动作** —— 撤回 / 终止 / 追加字段这类
   不挂在任务上的动作写 `0` 而非 `NULL`（免去 `COALESCE(task_id,0)` 生成列，
   因为 SQLite 不支持生成列；见 TECH-DESIGN §3 与 `app/models/audit.py`）。
6. **纯核心不许 import `db`** —— 见 §2.3 的现状说明。要碰数据库就写在 `service.py`，
   或者把查询做成 `services` 层的实现、通过 `ApproverProvider` 这类协议注入。
