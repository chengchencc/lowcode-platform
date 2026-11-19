# FlowForm 浏览器 E2E（Playwright）

这是 **G2 业务旅程** 的执行层：真实后端 + 真实数据库 + 真实浏览器，多角色同时在线。

> 新增/修改 E2E 的完整流程与检查清单见 [../plan/TESTING-GUIDE.md](../plan/TESTING-GUIDE.md) §4。

## 前置

```bash
cd testing/e2e
npm install
```

Windows 默认直接用系统 **Edge**（`channel=msedge`），不需要下载 Chromium。
其他平台或想用自带 Chromium 时：

```bash
npx playwright install chromium
E2E_BROWSER_CHANNEL=bundled npm test
```

也可用 `E2E_BROWSER_CHANNEL=chrome` 指定系统 Chrome。

## 运行

```bash
# 推荐入口：重置独立库 → 起后端/前端 → 跑 Playwright
bash scripts/e2e.sh

# 只跑 P0
bash scripts/e2e.sh @p0

# 打开真实浏览器，逐步可见（推荐前期人工观察）
bash scripts/e2e.sh @p0 --headed

# 交互式调试 UI
bash scripts/e2e.sh --ui

# 保留 testing/.runtime/e2e 数据
bash scripts/e2e.sh --no-reset

# 复用已启动的 8000/5173 服务
bash scripts/e2e.sh --no-server
```

直接跑（服务已启动时）：

```bash
cd testing/e2e
npm test
npm test -- --grep @p0
npm run report
```

## 环境

- 独立数据库：`testing/.runtime/e2e/e2e.db`（`testing/scripts/e2e-reset.sh` 创建；绝不碰 `backend/flowform.db`）
- 独立附件目录：`testing/.runtime/e2e/storage/`
- 账号：见 `testing/.runtime/e2e/accounts.md` 或 `../acceptance/TEST-DATA.md`
- 失败产物：`testing/.runtime/test-results/`（trace/screenshot；视频默认关闭）
- HTML 报告：`testing/.runtime/playwright-report/`

需要录屏时：`npx playwright install ffmpeg`，然后 `E2E_VIDEO=1 bash scripts/e2e.sh`。

这些目录已在 `.gitignore` 中，不会提交。

## 约定

- 定位器优先 `getByRole` / `getByLabel` / `getByPlaceholder` / `getByText`；动态列表可加 `data-testid`，但**禁止**依赖 antd 内部 class。
- UI 只走被验证的关键交互；造数/前置状态用 `fixtures/auth.ts` 的 API 登录与后续 API 工厂。
- 每条用例断言用户可见结果；权限类用例同时断言 UI 不显示 + API 403。
- 用例之间不共享可变数据；共享实例的多角色用例用 `test.describe.serial`。
- 首轮 `workers=1`；数据命名空间稳定后再提高并行度。
- flaky 用例必须修，不能靠 retry 掩盖。

## 目录

```text
testing/e2e/
├─ playwright.config.ts
├─ fixtures/
│  ├─ auth.ts          # 多角色 API 登录 / storageState
│  ├─ data.ts          # 请假样例实例、render 断言
│  ├─ factories.ts     # 自建表单/流程/实例的 API 工厂
│  └─ ui.ts            # 待办定位、同意/驳回等公共交互
├─ specs/
│  ├─ smoke.spec.ts
│  ├─ design.spec.ts
│  ├─ initiate.spec.ts
│  ├─ approve.spec.ts
│  ├─ reject-resubmit.spec.ts
│  ├─ parallel-countersign.spec.ts
│  ├─ condition-branch.spec.ts
│  ├─ permissions.spec.ts
│  ├─ lifecycle.spec.ts
│  ├─ ext-field.spec.ts
│  ├─ search-archive-export.spec.ts
│  ├─ transfer-delegation.spec.ts
│  ├─ notifications.spec.ts
│  ├─ search-filter.spec.ts
│  ├─ timeline-snapshot.spec.ts
│  └─ mobile-print.spec.ts
├─ package.json
└─ tsconfig.json
```

## 当前状态

- `bash scripts/e2e.sh @p0`：**37 passed**（2026-11-20，R17）。
- TEST-PLAN §7.6 的 12 条核心旅程已全部有可重复执行的用例。
- 打印只验证入口调用；A4 排版、图形化设计器的条件/并行/权限配置、跨浏览器仍待补。
