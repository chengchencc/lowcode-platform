# Spec Pack 与独立用例设计

## 为什么需要

现有测试与实现同源：代码怎么写，测试就断言什么。要回答"行为是否符合需求"，必须换一个**不知道实现**的上下文来设计用例。Spec Pack 就是给这个独立上下文的最小资料包。

## 包含什么

`bash scripts/build-spec-pack.sh` 会生成 `testing/.runtime/spec-pack/`（已 gitignore，不提交）：

```text
testing/.runtime/spec-pack/
├─ README.md                 # 资料清单与设计规则
├─ docs/
│  ├─ PRD-lowcode-form-approval.md
│  ├─ TECH-DESIGN.md         # 设计决策、状态机、权限矩阵、API 契约
│  ├─ PHASE2-DESIGN.md
│  ├─ PHASE3-DESIGN.md
│  ├─ DEMO.md
│  ├─ REQ-OPT-FLOW-CONFIG.md
│  ├─ SEARCH-FILTER-PLAN.md
│  ├─ TEST-PLAN.md           # §6 的 P0 场景基线
│  ├─ business-charter.md    # 从业务章程 docx 抽取的文本
│  ├─ TEST-DATA.md
│  └─ TEMPLATE.md
└─ api/
   └─ openapi.json           # 只作接口契约，不作为业务规则来源
```

**不包含**：`backend/`、`frontend/`、`testing/e2e/` 的任何源码、测试代码或实现文件。

## 独立设计 Prompt（复制给新会话/子代理）

```text
你是一名独立测试设计师。你的任务是为 FlowForm 设计 P0 验收用例。

【资料边界】
- 只能阅读 testing/.runtime/spec-pack/ 目录下的文件。
- 禁止读取 backend/、frontend/、testing/e2e/、scripts/ 或任何源码/测试代码。
- OpenAPI 只用于确认接口路径、请求/响应字段与状态码；不要从字段名反推业务规则。

【设计规则】
- 期望结果只能来自 PRD、TECH-DESIGN、PHASE2/3 设计、业务章程、DEMO、TEST-PLAN §6，
  以及文档中明确的用户确认结论。
- 禁止根据“系统通常会怎么做”或“现有实现可能怎么做”补规则。
- 文档没有定义清楚的，列在“需求待确认项”，不要自己发明。
- 每条用例必须有需求来源；每个核心机制至少一条正向 + 一条反向（越权/非法状态/重复操作）。
- 期望结果必须是可观察、可断言的：页面文本、URL、状态码、字段值、任务数、通知数、审计记录。
- 前置条件不能依赖其他用例的执行顺序。

【输出】
- 按 testing/.runtime/spec-pack/docs/TEMPLATE.md 的模板输出 Markdown。
- 覆盖 testing/.runtime/spec-pack/docs/TEST-PLAN.md §6 的 P0 场景 ID：
  AUTH/ORG/FORM/FLOW/PERM/INIT/TASK/REJECT/RETURN/WITHDRAW/TERMINATE/CC/EXT/NOTIFY/SEARCH/ARCHIVE/DASH。
- 每个场景至少 1 条；会拆成多条时用 -a/-b 后缀。
- 先输出一份“需求歧义与待确认清单”，再输出用例。
```

## 评审与执行

1. 产品负责人只审 **P0 用例的"期望结果"** 和"需求待确认项"。
2. 主会话把确认后的用例落到 `testing/acceptance/*.md`，同步 `testing/acceptance/ACCEPTANCE-MATRIX.md`。
3. 执行顺序：API 黑盒 → 浏览器 E2E → 手工补充。
4. 用例失败时按 `testing/plan/TEST-PLAN.md` §11 三角定位；需求歧义先改文档，再改用例和代码。

## 维护

- Spec Pack 是生成物，不提交；需求文档变化后重新执行 `scripts/build-spec-pack.sh`。
- 用例文件是提交物；每次需求变更都要检查受影响的用例。
