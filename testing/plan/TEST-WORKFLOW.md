# 新特性测试工作流与运行节奏

> 建立：2026-11-20
> 目的：每加一个特性，知道「该补哪层测试、跑哪条命令、什么时候跑全量」，避免两种浪费——只跑单测就宣布完成，或每次改动都全量跑一遍。
> 配套：`TEST-PLAN.md`（战略）、`../../docs/PROJECT-PLAN.md`（剩余验证、GitHub 迁移与 CI）。

## 1. 四条原则

1. **在缺陷所在的层测试**：引擎语义用单测/API；界面语义用浏览器 E2E；不拿组件测试冒充验收。
2. **需求先于实现**：新特性先写 Given/When/Then 验收点（Spec-only），再写代码。
3. **每个 bug 变一条回归用例**：先补按期望行为写的失败用例，再修。
4. **单测全绿 ≠ 验收通过**：验收只认需求矩阵 + 真实旅程。

## 2. 新特性交付流程（DoD）

| 步骤 | 产出 | 放置位置 |
|---|---|---|
| 1. 明确期望 | 验收点 + 需求来源；歧义先回写 PRD/设计文档 | `acceptance/ACCEPTANCE-MATRIX.md` 新行 |
| 2. 后端实现 | 单元/集成测试 | `backend/tests/test_*.py` |
| 3. 接口契约 | API 黑盒用例（不 import 实现） | `testing/api/test_*.py` |
| 4. 前端逻辑 | 组件/纯函数测试 | `frontend/src/**/*.spec.ts` |
| 5. 用户可见旅程 | Playwright 用例（造数走 API） | `testing/e2e/specs/*.spec.ts` |
| 6. 收尾 | 矩阵状态、报告、必要文档 | `acceptance/`、`reports/` |

**完成定义**：以上适用项全部有；`check.sh` 全绿；受影响 API/E2E 绿；矩阵已更新。

## 3. 按改动类型选测试

| 改动类型 | 必跑 | 按需 |
|---|---|---|
| 后端业务/接口 | `check.sh backend tests/test_x.py`；对应 API 文件 | 权限/导出类再跑 E2E |
| 引擎/流程语义（会签、条件、退回…） | 引擎单测 + `api.sh test_custom_flows.py` | G3 随机序列（建立后） |
| 表单/流程设计器 | `definitionOps.spec.ts` 等 vitest；`e2e.sh specs/design.spec.ts` | 设计器复杂配置 E2E |
| 字段权限/可见性 | `api.sh test_permissions.py test_snapshots.py`；`e2e.sh specs/permissions.spec.ts` | 打印/导出专项 |
| 只改文案/样式 | `check.sh frontend`；受影响 E2E | 人工看截图 |
| 依赖/构建/部署 | `check.sh` 全量 + Docker 冒烟（环境可用时） | 三库矩阵 |

## 4. 命令速查（当前实测）

| 命令 | 内容 | 耗时（本机） |
|---|---|---|
| `bash scripts/check.sh quick` | ruff + vue-tsc + vitest | 约 1 分钟 |
| `bash scripts/check.sh backend tests/test_x.py` | 指定后端测试 + ruff | 数十秒 |
| `bash scripts/check.sh backend` | 全量 pytest + ruff | 约 1.5–2 分钟 |
| `bash scripts/check.sh frontend` | vue-tsc + vitest + build | 约 1 分钟 |
| `bash scripts/check.sh` | 全部五项 | 约 2.5 分钟 |
| `bash scripts/api.sh` | 重置独立库 + 起后端 + 71 条 API | 约 50 秒 |
| `bash scripts/api.sh -k hidden` | 只跑匹配用例 | 约 20 秒 |
| `bash scripts/e2e.sh specs/approve.spec.ts` | 重置 + 起前后端 + 单文件 | 约 20–40 秒 |
| `bash scripts/e2e.sh @p0` | 全量 P0 旅程（37 条） | 约 2 分钟 |

> `api.sh` 与 `e2e.sh` 共用 `testing/.runtime/e2e` 和 8000/5173 端口，**不要并行跑**。

## 5. 运行节奏

| 时机 | 跑什么 | 目标 |
|---|---|---|
| 迭代中（每 15–30 分钟） | `check.sh quick` + 受影响单测 | < 2 分钟 |
| 提交前 | `check.sh quick` + 受影响 API/E2E 文件 | 3–5 分钟 |
| 合并到主分支 / PR | 全量 `check.sh` + `api.sh` + `e2e.sh @p0`（CI 并行） | 6–8 分钟 |
| 每晚（nightly） | 全量 E2E + G3 随机序列 + MySQL/PG 矩阵 + 性能冒烟 | 20–30 分钟 |
| 发布前 | 以上全部 + Docker 全新部署 + UAT + 打印人工验收 | 半天 |

**Bug 修复期间**：只改代码 + 补一条失败用例；不在中途反复跑全量单测，收尾统一跑 `check.sh`。

## 6. 标签与筛选

- E2E 用 `@p0` 标记试用前必须绿的旅程；后续加 `@p1`、`@slow`、`@smoke`，用 `--grep` 选择。
- API 用文件名 / `-k` 选择；保持「一个场景一个文件」的粒度。
- 新增 E2E 默认带 `@p0`，除非明确属于 P1/P2。

## 7. 数据与环境隔离

- API/E2E 只连 `testing/.runtime/e2e/e2e.db` 与独立附件目录，绝不碰 `backend/flowform.db`。
- 每次运行先重置；用例内用 API 工厂造数，不依赖执行顺序。
- 唯一数据带运行前缀/时间戳，便于搜索与清理。
- CI 每次都是全新环境，等价于 `--reset`。

## 8. 失败判定与闭环

1. 先判断是**实现 bug / 用例错误 / 需求歧义**，不直接改用例迁就实现。
2. 实现 bug：按模板登记，补失败用例 → 修 → 转绿。
3. 需求歧义：先更新 PRD/设计文档与决策表，再动代码和用例。
4. 每轮结束更新 `ACCEPTANCE-MATRIX.md` 与对应报告。

## 9. 效率建议

- 单文件调试优先 `api.sh <file>` / `e2e.sh specs/<file>`，不要每次全量。
- E2E 造数尽量走 API，UI 只走被验证的关键交互，降低脆性。
- 共享公共交互（登录、待办定位、同意/驳回）放 `testing/e2e/fixtures/`，避免复制。
- 失败产物默认在 `testing/.runtime/test-results/`；先看截图/error-context，再看 trace。
- 全量跑之前确认端口空闲；`e2e.sh` 退出会自动清理。
