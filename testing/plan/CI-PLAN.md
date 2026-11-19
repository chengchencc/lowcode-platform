# GitHub Actions 测试流水线规划

> 建立：2026-11-20
> 现状：仓库托管在 Gitee；测试入口已脚本化（`check.sh` / `api.sh` / `e2e.sh`），具备直接搬进 CI 的条件。
> 目标：PR 快速反馈、nightly 环境矩阵、发布前完整回归；不重复跑、不无限加机器。

## 1. 迁移前置

| 事项 | 说明 |
|---|---|
| GitHub 仓库 | 新建仓库并切换 remote；可保留 Gitee 作为镜像（两边手动 push 或镜像同步） |
| Actions 开启 | 私有仓库注意免费额度；公开仓库免费但定时任务长期无提交会被暂停 |
| 运行环境 | `ubuntu-latest` + Python 3.12 + Node 22；E2E 用 Playwright bundled Chromium |
| 浏览器配置 | CI 设 `E2E_BROWSER_CHANNEL=bundled`，避免依赖 Windows Edge |
| 数据库覆盖 | `testing/scripts/e2e-env.sh` 需支持外部 `E2E_DATABASE_URL`（当前硬编码 SQLite），供 nightly MySQL/PG 使用 |
| 分支保护 | `master` 要求 PR + CI 必需检查通过；禁止直接 push |

## 2. 工作流拆分

| 工作流 | 触发 | 内容 | 目标耗时 |
|---|---|---|---|
| `ci.yml` | PR / push master | 后端 pytest+ruff、前端 typecheck+vitest+build、API 黑盒、E2E `@p0` | 6–8 分钟 |
| `nightly.yml` | 每日定时 / 手动 | 全量 E2E、G3 随机序列、MySQL 8 + PG16 矩阵、性能冒烟 | 20–30 分钟 |
| `docker.yml` | 手动 / 发布标签 / 部署相关改动 | 构建 backend/frontend 镜像，compose 起服务并打 `/readyz` | 8–12 分钟 |
| `release.yml` | `v*` 标签 | 构建并推送 GHCR 镜像、生成发布说明 | 5–10 分钟 |
| `security.yml` | PR / 每周 | CodeQL（Python/TS）+ 依赖审查（可选，低优先级） | 5 分钟 |

> 当前不把所有工作流一次性建好：先上 `ci.yml`，稳定后再加 nightly 与发布。

## 3. `ci.yml` 设计

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

- 四个 job 并行；API 与 E2E 各自拥有独立 runner，不抢 8000/5173 端口。
- 缓存 pip / npm；Playwright 浏览器可按 `@playwright/test` 版本加缓存（后期再优化）。
- 失败保留 `error-context.md`、截图与 trace，作为 artifact 上传。
- `paths` 过滤可按 `backend/**`、`frontend/**`、`testing/**`、`docs/**` 拆分，减少无关运行。

## 4. `nightly.yml` 设计

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
- 需要先给 `e2e-env.sh` 加 `E2E_DATABASE_URL` 覆盖；否则脚本会强行指回 SQLite。
- MySQL 用例中当前 skip 的「转办 vs 同意」在此环境自动转绿，是 CONC-01 的落地位置。
- G3 不变量建立后，nightly 跑 2,000 轮；失败保留 seed 与最小复现。

## 5. `docker.yml` / `release.yml`

- `docker.yml`：`docker build` 两个镜像；`docker compose up -d` 后轮询 `/api/v1/readyz`，再跑一次登录/发起/审批冒烟；失败上传容器日志。
- `release.yml`：标签触发，`docker/build-push-action` 推 `ghcr.io/<owner>/flowform-backend|frontend`，附 release notes。
- 这两个工作流建议在 `ci.yml` 稳定后再开，避免早期同时调试 CI 与镜像。

## 6. 缓存与成本

| 项 | 建议 |
|---|---|
| pip | `actions/setup-python` 内置缓存 |
| npm | `actions/setup-node` 缓存，多 lockfile 用 `cache-dependency-path` 列表 |
| Playwright | 缓存 `~/.cache/ms-playwright`，key 用包版本；`--with-deps` 仍要装系统依赖 |
| 并发 | PR 用 `concurrency` 取消旧运行 |
| 路径过滤 | 文档改动不触发 E2E；后端改动不重复跑前端构建 |
| 私有额度 | 若分钟数紧张：nightly 降频为每周、DB 矩阵仅 MySQL、或接自托管 runner |

## 7. 落地顺序

1. **迁移仓库**：GitHub 新建、remote 切换、推送 `master` 与 `f_aitest`。
2. **最小 CI**：只跑 `backend` + `frontend` 两个 job，确认环境可复现。
3. **加 API 与 E2E job**：修 Linux 差异（浏览器、venv、端口），稳定 3 次后设为必需检查。
4. **分支保护 + PR 模板**：合并 `f_aitest` 走第一次完整 PR。
5. **nightly**：先 SQLite 全量 E2E，再加 MySQL/PG 矩阵。
6. **Docker/Release**：环境验证通过后再上。
7. **安全扫描**：最后按需加 CodeQL / Dependabot。

## 8. 明确不做

- 不在每个 PR 跑 MySQL/PG 矩阵（成本高、收益低；nightly 足够）。
- 不在 PR 跑 1 万实例性能压测（数据造数久；nightly/发布前跑）。
- 不把 UAT、打印排版、移动端观感塞进 CI（人工验收）。
- 不追求像素级截图对比（当前收益低于维护成本）。
