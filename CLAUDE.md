# CLAUDE.md

本文件面向在本仓库工作的 AI / 开发者，只放「如何安全、高效地改这个项目」。
需求、设计、部署细节以 `docs/` 为准；测试资产以 `testing/` 为准。

## 项目速览

FlowForm 是单组织内部的低代码表单 + 审批流平台：

- 后端：FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2，Python 3.12
- 前端：Vue 3 + TypeScript + Vite 6 + Ant Design Vue 4 + Pinia
- 数据库：开发期 SQLite；目标 MySQL 8 / PostgreSQL 16
- 认证：JWT + bcrypt；`token_version` 支持改密/停用即时踢下线

先读：

- 需求：`docs/PRD-lowcode-form-approval.md`
- 技术设计（含引擎、API、里程碑、已知陷阱）：`docs/TECH-DESIGN.md`
- 引擎代码地图：`docs/ENGINE.md`
- 二期 / 三期：`docs/PHASE2-DESIGN.md`、`docs/PHASE3-DESIGN.md`
- 测试总入口：`testing/README.md`
- 验收矩阵：`testing/acceptance/ACCEPTANCE-MATRIX.md`
- 后续计划：`docs/PROJECT-PLAN.md`

## 常用命令

```bash
# 环境（幂等）
bash scripts/setup.sh

# 本地启动
bash scripts/dev-backend.sh     # http://127.0.0.1:8000
bash scripts/dev-frontend.sh    # http://localhost:5173

# G0：单测 / 类型 / 构建
bash scripts/check.sh quick                     # ruff + vue-tsc + vitest，约 1 分钟
bash scripts/check.sh backend tests/test_x.py   # 只跑指定后端测试
bash scripts/check.sh                           # 全量五项，约 2.5 分钟

# G3：引擎不变量随机序列（默认 200 轮）
bash scripts/invariants.sh

# G1：API 黑盒（重置独立库 + 起后端 + pytest）
bash scripts/api.sh
bash scripts/api.sh -k hidden

# G2：浏览器旅程（重置独立库 + 起前后端 + Playwright）
bash scripts/e2e.sh @p0                 # 全量 P0
bash scripts/e2e.sh specs/approve.spec.ts
bash scripts/e2e.sh @p0 --headed        # 可见方式运行
```

`api.sh` 与 `e2e.sh` 共用 `testing/.runtime/e2e` 和 8000/5173 端口，**不要并行跑**。

## 新特性怎么测试

固定顺序，不要跳层：

1. **先写验收点**：从 PRD/设计文档推导 Given/When/Then，在 `testing/acceptance/ACCEPTANCE-MATRIX.md` 建行，标注需求来源。
2. **后端实现 + 单测**：`backend/tests/test_*.py`；只跑受影响文件。
3. **API 黑盒**：`testing/api/test_*.py`，只走 HTTP、不 import 业务实现。
4. **前端逻辑**：`frontend/src/**/*.spec.ts`（vitest）。
5. **用户可见旅程**：`testing/e2e/specs/*.spec.ts`；造数走 `fixtures/factories.ts`，UI 只走关键交互。
6. **收尾**：更新矩阵/报告；全量测试在**当天收尾 / 合并前 / 发布前**跑，不在每次小修后跑。

完成定义：适用层都有用例；**受影响用例转绿**；全量门禁在收尾时通过；矩阵状态已更新。

### 测试规模：按改动大小选最小充分集（重要）

**不要每改一个小问题就全量跑测试。** 按下面四档选择：

| 改动 | 只跑 | 禁止 |
|---|---|---|
| 单点 bug / 文案 / 样式 / 单个页面交互 | 受影响单测文件 + 1 条对应 E2E spec | 顺手跑全量 `check.sh` / API / E2E |
| 单个后端服务/接口 | `check.sh backend tests/test_x.py` + 对应 API 文件 | 全量 pytest |
| 跨前后端、权限、导出、状态机、引擎语义 | 受影响单测 + 对应 API 文件 + 受影响 E2E | 无差别全量 |
| 当天收尾 / 合并 / 发布 | 全量 `check.sh` + `api.sh` + `e2e.sh @p0` + `invariants.sh` | — |

判定规则：改动是否触及**引擎、权限、导出、状态机、快照**？是 → 升一级；否 → 停在最小集。

### Bug 修复的标准节奏

1. 先复现，补一条按期望行为写的失败用例。
2. 改代码。
3. **只跑这条用例 + 同文件相邻用例**，转绿即可。
4. 让用户在当前环境复测；不要中断去跑全量。
5. 当天收尾或合并前，再统一跑全量门禁。

UAT 期间尤其如此：每次修复只重启本地服务、交给你复测；全量留到收尾。

| 改动类型 | 必跑 |
|---|---|
| 后端业务/接口 | `check.sh backend tests/test_x.py` + 对应 API 文件 |
| 引擎/流程语义 | 引擎单测 + `api.sh test_custom_flows.py` |
| 表单/流程设计器 | 相关 vitest + `e2e.sh specs/design.spec.ts` |
| 字段权限/可见性 | `api.sh test_permissions.py test_snapshots.py` + `e2e.sh specs/permissions.spec.ts` |
| 文案/样式 | `check.sh frontend` + 受影响 E2E |
| 依赖/部署 | 全量 `check.sh` + Docker 冒烟（环境可用时） |

运行节奏、耗时预算、完整选层表见 `testing/plan/TEST-WORKFLOW.md`。

## 工作规则（重要）

- **需求歧义先改文档**：先更新 PRD/设计文档与决策表，再改代码和用例。不要用实现反推期望。
- **Bug 修复**：先补一条按期望行为写的失败用例，再修；只跑该用例与相邻用例。**修复期间禁止反复跑全量单测**，全量留到当天收尾/合并前。
- **测试效率**：小修小跑、大改中跑、收尾全跑；不要用“全量绿”替代定向回归。
- **界面改动由用户验证**：需要看效果时把地址/路径交给用户；不要擅自启动 Docker 这类本地服务。
- **数据隔离**：API/E2E 只连 `testing/.runtime/e2e`，绝不碰 `backend/flowform.db`；测试数据用唯一前缀。
- **不拿单测全绿当验收**：验收只认需求矩阵 + 真实旅程。
- **提交**：信息用中文，沿用 `type(scope): 摘要`；只在你确认的检查点提交，推送前确认。
- **测试优先级**：P0 业务链路优先；P1/P2 按 `docs/PROJECT-PLAN.md` 排期。

## 代码结构速记

- `backend/app/api/v1/`：路由层，只做参数/权限依赖与调用 service
- `backend/app/services/`：业务服务；实例、渲染、导出、检索等
- `backend/app/engine/`：流程引擎（状态机、令牌、权限、通知）
- `backend/alembic/versions/`：迁移；新增表必须写迁移
- `frontend/src/views/`：页面；`components/`：复用组件；`api/`：请求模块
- `testing/api/`：G1 黑盒；`testing/e2e/`：G2 Playwright；`testing/scripts/`：运行脚本

## 当前状态（2026-11-20）

- G1 API 黑盒：94 passed + 3 MySQL-only skipped。
- G2 浏览器旅程：41 passed（12 条 P0 核心旅程全覆盖）。
- G3 引擎不变量：200 轮随机序列通过。
- 全量 `check.sh`：452 pytest + 128 vitest + ruff / vue-tsc / build 全绿。
- 剩余：Docker MySQL/PG、迁移/时区、性能、UAT、A4 打印；详见 `docs/PROJECT-PLAN.md`。
