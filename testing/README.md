# FlowForm 验收测试

这里集中放**本次新增的、跨模块的验收测试资产**：策略、验收用例、E2E、运行脚本、测试报告。

## 不在这里

- `backend/tests/`、`frontend/src/**/*.spec.ts`：G0 单元/集成测试，跟代码走。
- `scripts/check.sh`：G0 校验入口。
- `docs/formula-test-vectors.json`、`docs/form-rule-test-vectors.json`：前后端共享语义向量。
- `docs/PRD-lowcode-form-approval.md`、`docs/TECH-DESIGN.md` 等产品/设计文档。

## 目录

| 路径 | 内容 |
|---|---|
| `plan/TEST-PLAN.md` | 总体测试战略、四道闸门、退出标准 |
| `plan/TESTING-GUIDE.md` | 新增/修改/回归测试的操作手册 |
| `acceptance/ACCEPTANCE-MATRIX.md` | 需求→用例→结果，唯一验收口径 |
| `acceptance/P0-DECISIONS.md` | 已确认决策、实现默认、文档冲突 |
| `acceptance/P0-CASES-*.md` | 三份 P0 用例草案（132 条 + 38 项检查） |
| `acceptance/README.md` | G1 用例规则与状态流转 |
| `acceptance/SPEC-PACK.md` | 独立用例设计（Spec Pack）流程 |
| `acceptance/TEMPLATE.md` | 单条用例模板 |
| `acceptance/TEST-DATA.md` | 测试账号、组织、种子数据 |
| `api/` | G1 API 黑盒验收（pytest + HTTP，不 import 业务实现） |
| `e2e/` | Playwright 工程（真实浏览器多角色旅程） |
| `scripts/` | Spec Pack 构建、API/E2E 启动与重置 |
| `.runtime/` | 生成物（gitignore）：Spec Pack、E2E 库、报告 |

## 快速开始

```bash
# G1 API 黑盒（重置独立库 → 起后端 → pytest）
bash scripts/api.sh
bash scripts/api.sh -k hidden

# 带界面跑 P0 冒烟（会打开 Edge）
bash scripts/e2e.sh @p0 --headed

# 无头回归
bash scripts/e2e.sh @p0

# 构建独立设计用的 Spec Pack
bash scripts/build-spec-pack.sh

# 重置 E2E 独立库
bash testing/scripts/e2e-reset.sh

# G0 校验（原有单元/集成测试）
bash scripts/check.sh
```

`scripts/e2e.sh` 和 `scripts/build-spec-pack.sh` 是兼容入口，真实脚本在 `testing/scripts/`。

## 当前状态

- Phase 0 骨架完成；R0 工程冒烟 6/6。
- P0 用例设计完成：132 条 + 38 项非功能检查，覆盖 44 个 P0 场景；D-01–D-05 已确认并回写文档。
- G1 API 黑盒已执行 71 条（另有 1 条 MySQL-only skipped），累计修复 13 个缺陷（含 1 个 S1 转办卡死）；已覆盖表单/流程设计、全域权限、发起范围、审批人来源、扩展字段、安全、SEARCH、附件、快照、并发、通知、首页口径。
- G2 浏览器旅程 R17：**36/36 通过**，TEST-PLAN §7.6 的 12 条核心旅程全部落地（含快照/移动/打印冒烟）。
- 剩余 P0 主要是 Docker/MySQL/PG、迁移/时区、性能、UAT、打印排版；转办并发需 MySQL；SEARCH 编号语义与 ARCHIVE 列序属界面/格式验收。
- E2E 未覆盖项与观察见 [reports/2026-11-20-p0-e2e-r17.md](reports/2026-11-20-p0-e2e-r17.md)。
- 详见 [plan/TEST-PLAN.md](plan/TEST-PLAN.md)、[acceptance/P0-DECISIONS.md](acceptance/P0-DECISIONS.md) 与 [acceptance/ACCEPTANCE-MATRIX.md](acceptance/ACCEPTANCE-MATRIX.md)。
