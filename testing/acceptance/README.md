# 验收用例库（G1）

本目录是 **G1 需求验收** 的唯一用例来源。它回答的问题不是"代码有没有按写的逻辑跑"，而是"代码行为是否符合 PRD、真实业务流程和用户确认的期望"。

> 新增/修改测试的完整操作流程见 [../plan/TESTING-GUIDE.md](../plan/TESTING-GUIDE.md)。

## 铁律

1. **设计用例时不读实现源码**（`backend/`、`frontend/`、`testing/e2e/`）。只看 `testing/.runtime/spec-pack/` 里的需求、设计、业务文档和 OpenAPI 契约。
2. **期望结果只能来自需求/业务/用户确认**，不能来自"当前系统实际怎么表现"。
3. 每条用例必须标注需求来源；找不到来源的，标记为"需求待确认"，先问产品负责人。
4. 用例失败时先判断：实现 bug / 需求歧义 / 用例错误。需求歧义要回写 PRD 或设计文档，不能私自在用例里"解释"。
5. 用户发现的每个缺陷，修复前必须先补一条按期望行为写的失败用例。

## 目录约定

| 文件 | 内容 |
|---|---|
| `TEMPLATE.md` | 单条用例模板 |
| `SPEC-PACK.md` | Spec Pack 的构建方法、独立设计 Prompt、评审流程 |
| `TEST-DATA.md` | 测试角色、组织、种子数据、数据重置 |
| `01-auth-org.md` | AUTH / ORG |
| `02-form.md` | FORM |
| `03-flow.md` | FLOW |
| `04-permission.md` | PERM / SEC |
| `05-initiate-task.md` | INIT / TASK |
| `06-exception.md` | REJECT / RETURN / WITHDRAW / TERMINATE / CC / EXT / NOTIFY |
| `07-search-archive.md` | SEARCH / ARCHIVE / DASH |
| `08-nonfunctional.md` | CONC / ENV / PERF / UAT |
| `09-p1.md` | SHEET / AI / PRINT / MOBILE（P1） |

用例文件按需创建；没有设计的场景先在 `ACCEPTANCE-MATRIX.md` 里保持 `TODO`。

## 用例 ID

- 场景 ID 沿用 `../plan/TEST-PLAN.md` §6：`REJECT-01`、`PERM-01`……
- 同一场景拆成多条用例时加后缀：`REJECT-01-a`、`REJECT-01-b`。
- 用例 ID 一旦被自动化引用就不再改名；要拆分时新增 ID，旧 ID 标记 `N/A` 并注明替代者。

## 状态流转

```text
TODO（未设计）
  → DESIGNED（用例已写，待执行）
  → AUTOMATED（已进 API/E2E 套件）
  → PASS / FAIL（最近一次执行结果）
  → BLOCKED（环境/依赖阻塞）
```

`ACCEPTANCE-MATRIX.md` 是唯一汇总口径。代码覆盖率、单元测试通过数**不能**替代这里的完成度。

## 标准工作流

1. 构建隔离的 Spec Pack：

   ```bash
   bash scripts/build-spec-pack.sh
   ```

2. 在**全新上下文**中，只把 `testing/.runtime/spec-pack/` 交给测试设计者，按 `SPEC-PACK.md` 的 Prompt 输出用例。
3. 把用例落到本目录对应的模块文件，并同步更新 `ACCEPTANCE-MATRIX.md`。
4. **产品负责人确认 P0 用例的"期望结果"**（只看期望，不需要审步骤细节）。
5. 主会话执行：API 黑盒优先，界面旅程进 Playwright。
6. 失败用例按 `../plan/TEST-PLAN.md` §11 判定根因、登记缺陷、补回归。

## 执行入口

| 层 | 命令 | 说明 |
|---|---|---|
| API 黑盒 | 待建 `testing/scripts/api-acceptance.sh` / pytest 标记 `@acceptance` | 只走 HTTP，不 import 业务实现 |
| 浏览器 E2E | `bash scripts/e2e.sh @p0` | 独立 `testing/.runtime/e2e/` 库、真实后端 + Vite |
| 手工/UAT | `testing/acceptance` 对应用例 | 产品负责人按步骤执行并签收 |
