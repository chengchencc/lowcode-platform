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
| `acceptance/README.md` | G1 用例规则与状态流转 |
| `acceptance/SPEC-PACK.md` | 独立用例设计（Spec Pack）流程 |
| `acceptance/TEMPLATE.md` | 单条用例模板 |
| `acceptance/TEST-DATA.md` | 测试账号、组织、种子数据 |
| `e2e/` | Playwright 工程（真实浏览器多角色旅程） |
| `scripts/` | Spec Pack 构建、E2E 启动/重置 |
| `.runtime/` | 生成物（gitignore）：Spec Pack、E2E 库、报告 |

## 快速开始

```bash
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
- 验收矩阵 44 个 P0 + 4 个 P1 场景，用例设计进行中。
- 详见 [plan/TEST-PLAN.md](plan/TEST-PLAN.md) 与 [acceptance/ACCEPTANCE-MATRIX.md](acceptance/ACCEPTANCE-MATRIX.md)。
