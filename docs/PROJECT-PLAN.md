# FlowForm 工程后续计划

> 建立：2026-11-20
> 定位：功能开发完成后的**验证收尾、测试补强、GitHub 迁移与 CI 落地**计划。
> 测试战略见 `testing/plan/TEST-PLAN.md`；日常测试流程见 `testing/plan/TEST-WORKFLOW.md`；验收状态以 `testing/acceptance/ACCEPTANCE-MATRIX.md` 为准。

## 0. 当前状态

| 项 | 状态 |
|---|---|
| 功能 | 一期 M1–M6、二期 M7–M10、三期 M11–M16 已实现 |
| G1 API 黑盒 | 94 passed + 3 MySQL-only skipped（3 条为 MySQL 并发专项） |
| G2 浏览器旅程 | 41 passed（12 条 P0 核心旅程全覆盖） |
| G0 全量校验 | 452 pytest + 128 vitest + ruff / vue-tsc / build 全绿 |
| G3 引擎不变量 | 200 轮随机序列通过（`bash scripts/invariants.sh`） |
| 分支 | `f_aitest`；待 CI 就绪后合入 `master` |

---

## 1. 剩余验证与测试

### 1.1 P0 环境与人工验收（当前阻塞）

| ID | 事项 | 阻塞原因 | 下一步 |
|---|---|---|---|
| ENV-01 | Docker MySQL 8 / PostgreSQL 16 全新部署、重启持久化、附件卷 | 等可用的 Docker（含 PG）机器 | `bash scripts/docker-up.sh` / `--postgres`，记录部署问题 |
| ENV-02 | 空库迁移、上一版本升级迁移；SQLite/MySQL/PG 核心链路一致 | 依赖 ENV-01 | 三库各跑一次「登录→发起→审批→归档」 |
| ENV-03 | UTC 存储与 Asia/Shanghai 展示边界、首页今日/本周/本月跨日 | 依赖 ENV-01 | API + 页面各验证一次边界时刻 |
| CONC-01 | 转办 vs 同意、自动派单并发（SQLite 已 skip） | 需 MySQL 行锁 | 在 MySQL 环境运行 `test_concurrency.py` 中被 skip 的用例 |
| PERF-01 | 1k/10k 实例列表与筛选、100 节点设计器、待办/首页基线 | 依赖环境与造数脚本 | 先造数再压测，记录 P95 与瓶颈 |
| UAT-01 | 产品负责人独立走查：配流程、发起审批、驳回重提、检索导出 | 人工 | 按 `testing/acceptance/TEST-DATA.md` 走一遍 |
| OFFLINE-01 | 内网镜像包：基础镜像已下载，应用镜像待构建 | 本机 Docker 守护进程不可用 | 按 `docs/OFFLINE-DEPLOY.md` 方式 A/B 生成并导入 |
| PRINT-01 | A4 打印分页、字段、时间线、hidden 字段 | 人工视觉验收 | 与 UAT 一起看；E2E 只验证了打印入口 |
| FORMAT-01 | 归档列序、表单编号与实例单号展示口径 | 人工/格式确认 | UAT 时确认是否符合业务阅读习惯 |

### 1.2 P0 自动化补测（本地可做，不依赖 Docker）

**E2E（已确认下一优先项）**

- [x] 设计器复杂配置：表单设计器预览；流程条件分支、并行组、字段权限矩阵的图形化配置与运行结果（R17）。
- [x] 委托创建 UI：RangePicker 生效时段（R17）。
- [x] 通知「≤10s 感知」轮询时延（R17）。
- [ ] Chrome（或 bundled Chromium）回归；当前只跑 Windows Edge。
- [x] 筛选器区间操作符（R17）；属于/为空/多选组合 UI 仍待补。

**API 黑盒子项**

| 场景 | 仍缺子项 |
|---|---|
| ORG-01 / ORG-02 | 角色成员 CRUD 与变更；运行中部门移动/角色变更对在途任务的影响 |
| FORM-02 / FORM-03 | 旧实例详情展示旧版；值规则、子表绕过前端伪造 |
| FLOW-02 / FLOW-03 | 孤儿节点、引用不存在字段、空分支的发布拦截；深嵌套；删除被引用字段 |
| PERM-01 | 分区批量权限 + 条件覆盖（`conditional_overrides`） |
| PERM-02 / PERM-04 | 打印视角 hidden 字段；hidden 字段附件的打印/导出路径 |
| PERM-03 / SEC-01 | 快照、导出、任务、附件全接口 IDOR 组合 |
| SEC-02 | 上传路径穿越、文件大小边界 |
| INIT-02 / INIT-03 / INIT-04 | 自动填充/标题/只读剩余组合；双会话重复提交；指定部门与上一节点来源 |
| TASK-01 / TASK-04 / TASK-05 / TASK-06 | 列表筛选/分页/会签合并；并行组提前推进/卡死边界；字段 diff 展示与附件下载权限；双会话并发处理 |
| TASK-07 | 转办/委托的通知、时间线、会签组内转办 |
| REJECT-01 / RETURN-01 | 快照差异对照（SnapshotDiff）；非法退回目标 |
| WITHDRAW-01 / TERMINATE-01 | 撤回/终止通知与时间线 |
| CC-01 | 抄送附件、hidden 字段、下载权限 |
| EXT-01 | 动态字段进入快照、追加字段通知去重 |
| NOTIFY-01 | 撤回/终止通知；≤10s 轮询 |
| SEARCH-01 / SEARCH-02 | 表单编号 vs 实例单号语义；跨版本检索一致性 |
| DASH-01 | 空状态、轮询刷新 |
| ARCHIVE-01 | 列序与格式（与 FORMAT-01 合并验收） |

> 说明：矩阵按整条场景计状态，标 `PARTIAL` 不代表全部未测；已由 R17 覆盖的子项（会签驳回、顺序退回、快照进入/退出、撤回守卫、转办 UI、筛选 UI、移动/打印入口等）不再重复列出。

### 1.3 G3 引擎不变量（已建立）

- [x] 已实现 `testing/invariants/`：随机流程 + 随机动作，检查状态机、任务守恒、重复派单、快照 seq、版本锁定等；200 轮通过。
- 运行：`bash scripts/invariants.sh`；`INVARIANT_ROUNDS=2000` 用于 nightly。
- 待扩展：权限单调性、审计完整性、更多退回/撤回组合。

### 1.4 P1 / P2 功能与测试

| ID | 事项 | 说明 |
|---|---|---|
| SHEET-01 | 共享表格：创建/编辑/自动保存/冲突/导出/权限 | P1，需 API + E2E |
| AI-01 | AI 生成表单/流程：默认关闭、校验、预览、限流、审计、失败兜底 | P1 |
| PRINT-01 | A4 打印排版 | P1，人工为主 |
| MOBILE-01 | 390px 其余页面（待办列表、消息、设计器） | P1，当前只覆盖发起/详情 |
| P2 | 视觉细节、极端性能、多浏览器像素一致性 | 可延后 |

---

## 2. GitHub 迁移与 Actions

### 2.1 迁移前置

| 事项 | 说明 |
|---|---|
| GitHub 仓库 | 新建仓库并切换 remote；可保留 Gitee 作为镜像 |
| Actions 开启 | 私有仓库注意免费额度；公开仓库免费，但定时任务长期无提交会被暂停 |
| 运行环境 | `ubuntu-latest` + Python 3.12 + Node 22；E2E 用 Playwright bundled Chromium |
| 浏览器配置 | CI 设 `E2E_BROWSER_CHANNEL=bundled`，避免依赖 Windows Edge |
| 数据库覆盖 | `testing/scripts/e2e-env.sh` 需支持外部 `E2E_DATABASE_URL`（当前硬编码 SQLite），供 nightly MySQL/PG 使用 |
| 分支保护 | `master` 要求 PR + CI 必需检查通过；禁止直接 push |

### 2.2 工作流拆分

| 工作流 | 触发 | 内容 | 目标耗时 |
|---|---|---|---|
| `ci.yml` | PR / push master | 后端 pytest+ruff、前端 typecheck+vitest+build、API 黑盒、E2E `@p0` | 6–8 分钟 |
| `nightly.yml` | 每日定时 / 手动 | 全量 E2E、G3 随机序列、MySQL 8 + PG16 矩阵、性能冒烟 | 20–30 分钟 |
| `docker.yml` | 手动 / 发布标签 / 部署相关改动 | 构建 backend/frontend 镜像，compose 起服务并打 `/readyz` | 8–12 分钟 |
| `release.yml` | `v*` 标签 | 构建并推送 GHCR 镜像、生成发布说明 | 5–10 分钟 |
| `security.yml` | PR / 每周 | CodeQL（Python/TS）+ 依赖审查（可选，低优先级） | 5 分钟 |

> 不要一次性建全：先上 `ci.yml`，稳定后再加 nightly 与发布。

### 2.3 `ci.yml` 设计

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [master]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: backend/requirements*.txt
      - run: python -m venv backend/.venv
      - run: backend/.venv/bin/pip install -r backend/requirements-dev.txt
      - run: bash scripts/check.sh backend

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci --prefix frontend
      - run: bash scripts/check.sh frontend

  api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: backend/requirements*.txt
      - run: python -m venv backend/.venv
      - run: backend/.venv/bin/pip install -r backend/requirements-dev.txt
      - run: bash scripts/api.sh

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: pip
          cache-dependency-path: backend/requirements*.txt
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
          cache-dependency-path: |
            frontend/package-lock.json
            testing/e2e/package-lock.json
      - run: python -m venv backend/.venv
      - run: backend/.venv/bin/pip install -r backend/requirements-dev.txt
      - run: npm ci --prefix frontend
      - run: npm ci --prefix testing/e2e
      - run: npx --prefix testing/e2e playwright install --with-deps chromium
      - run: E2E_BROWSER_CHANNEL=bundled bash scripts/e2e.sh @p0
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: playwright-report
          path: |
            testing/.runtime/playwright-report
            testing/.runtime/test-results
          retention-days: 7
```

要点：

- 四个 job 并行；API 与 E2E 各自独立 runner，不抢 8000/5173 端口。
- 缓存 pip / npm；Playwright 浏览器可按包版本追加缓存（后期优化）。
- 失败保留 `error-context.md`、截图与 trace，作为 artifact 上传。
- 可用 `paths` 过滤（`backend/**`、`frontend/**`、`testing/**`、`docs/**`），减少无关运行。

### 2.4 `nightly.yml` 设计

```yaml
name: nightly
on:
  schedule:
    - cron: '0 18 * * *'   # 北京时间次日 02:00
  workflow_dispatch:

jobs:
  e2e-full:
    runs-on: ubuntu-latest
    steps: [ ... 同 ci 的 e2e，跑全量（不加 @p0 grep） ... ]

  db-matrix:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        db: [mysql, postgres]
    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: root
          MYSQL_DATABASE: flowform
          MYSQL_USER: flowform
          MYSQL_PASSWORD: flowform
        ports: ['3306:3306']
        options: >-
          --health-cmd="mysqladmin ping -h 127.0.0.1 -uroot -proot"
          --health-interval=10s --health-timeout=5s --health-retries=12
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: flowform
          POSTGRES_USER: flowform
          POSTGRES_PASSWORD: flowform
        ports: ['5432:5432']
        options: >-
          --health-cmd="pg_isready -U flowform"
          --health-interval=10s --health-timeout=5s --health-retries=12
    steps:
      - ... 安装依赖 ...
      - run: |
          if [ "${{ matrix.db }}" = "mysql" ]; then
            export E2E_DATABASE_URL="mysql+pymysql://flowform:flowform@127.0.0.1:3306/flowform?charset=utf8mb4"
          else
            export E2E_DATABASE_URL="postgresql+psycopg://flowform:flowform@127.0.0.1:5432/flowform"
          fi
          bash scripts/api.sh testing/api/test_concurrency.py testing/api/test_custom_flows.py
```

要点：

- MySQL/PG 只在 nightly 跑核心链路与并发，不跑全量 E2E，控制时长。
- 需先给 `e2e-env.sh` 加 `E2E_DATABASE_URL` 覆盖；否则脚本会强行指回 SQLite。
- MySQL 用例中当前 skip 的「转办 vs 同意」在此环境自动转绿，是 CONC-01 的落地位置。
- G3 不变量建立后，nightly 跑 2,000 轮；失败保留 seed 与最小复现。

### 2.5 `docker.yml` / `release.yml`

- `docker.yml`：`docker build` 两个镜像；`docker compose up -d` 后轮询 `/api/v1/readyz`，再跑一次登录/发起/审批冒烟；失败上传容器日志。
- `release.yml`：标签触发，`docker/build-push-action` 推 `ghcr.io/<owner>/flowform-backend|frontend`，附 release notes。
- 建议在 `ci.yml` 稳定后再开，避免早期同时调试 CI 与镜像。

### 2.6 缓存、成本与落地顺序

| 项 | 建议 |
|---|---|
| pip | `actions/setup-python` 内置缓存 |
| npm | `actions/setup-node` 缓存，多 lockfile 用 `cache-dependency-path` 列表 |
| Playwright | 缓存 `~/.cache/ms-playwright`，key 用包版本；`--with-deps` 仍要装系统依赖 |
| 并发 | PR 用 `concurrency` 取消旧运行 |
| 路径过滤 | 文档改动不触发 E2E；后端改动不重复跑前端构建 |
| 私有额度 | 分钟数紧张时：nightly 降频、DB 矩阵仅 MySQL、或接自托管 runner |

落地顺序：

1. 迁移仓库：GitHub 新建、remote 切换、推送 `master` 与 `f_aitest`。
2. 最小 CI：只跑 `backend` + `frontend`，确认环境可复现。
3. 加 API 与 E2E job：修 Linux 差异（浏览器、venv、端口），稳定 3 次后设为必需检查。
4. 分支保护 + PR 模板：合并 `f_aitest` 走第一次完整 PR。
5. nightly：先 SQLite 全量 E2E，再加 MySQL/PG 矩阵。
6. Docker/Release：环境验证通过后再上。
7. 安全扫描：最后按需加 CodeQL / Dependabot。

### 2.7 明确不做

- 不在每个 PR 跑 MySQL/PG 矩阵（成本高、收益低；nightly 足够）。
- 不在 PR 跑 1 万实例性能压测（造数久；nightly/发布前跑）。
- 不把 UAT、打印排版、移动端观感塞进 CI（人工验收）。
- 不追求像素级截图对比（当前收益低于维护成本）。

---

## 3. 发布 / 内部试用检查清单

- [ ] P0 环境矩阵（MySQL / PG）与迁移验证通过。
- [ ] UAT 走查完成，问题已分级并关闭或给出绕行方案。
- [ ] S1 = 0；S2 清零或有明确排期。
- [ ] 全量 `check.sh` + `api.sh` + `e2e.sh @p0` 绿。
- [ ] 打印排版人工确认。
- [ ] 矩阵、报告、已知问题清单归档。
- [ ] 分支合入 `master`，打标签并生成发布说明。

## 4. 待确认

- 归档列序与编号展示口径（UAT 时确认）。
- 环境验证日期（等可用 Docker + PG 的机器）。
- GitHub 迁移后是否保留 Gitee 镜像。
