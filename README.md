# FlowForm

面向**单组织内部**的低代码表单 + 审批流平台：业务人员自助配置表单模板与审批流程，
发起人填表提交后系统按流程自动流转，支持顺序审批、并行会签、或签、条件分支、
动态审批人、驳回重提、抄送，并按节点控制字段的可见/可编辑权限，
让表单数据随审批逐节点丰富，全程留痕可审计。

> **当前进度：一期 M1–M6、二期 M7–M10、三期 M11–M16 均已实现。** 组织管理、
> 表单配置器、流程配置器与审批引擎、发起中心与工作台、实例详情（含驳回重提 /
> 快照对照 / 运行中追加字段）、示例流程库、归档检索与导出、操作审计全部可用；
> **PRD §9 场景一（请假）与场景二（报销）都已端到端跑通**。
> 二期增加流程可视化画布、表单布局/展示控件、字段联动规则、打印与移动端；
> 三期增加按角色首页、工作量统计协作表格、实例业务字段检索、转办与委托、AI 生成
> 表单/流程草稿。可交付内部试用 —— 部署看下面的「一键部署」，演示照着 `docs/DEMO.md` 走。
> 内网 / 离线部署（预下载镜像、docker load）见 `docs/OFFLINE-DEPLOY.md`。
>
> - 需求：`docs/PRD-lowcode-form-approval.md`
> - 设计：`docs/TECH-DESIGN.md`（含引擎设计、API 契约、里程碑排期、**已知陷阱**）
> - **二期设计**：`docs/PHASE2-DESIGN.md`（范围、里程碑、M7–M10 技术边界）
> - **三期设计**：`docs/PHASE3-DESIGN.md`（首页、工作量统计、台账检索、转办委托、AI）
> - **引擎代码说明**：`docs/ENGINE.md`（模块地图、一次事件的调用链、改一处跑哪个测试）
> - **AI 开发指南**：`CLAUDE.md`（常用命令、新特性测试流程、工作规则）
> - **测试总入口**：`testing/README.md`（验收测试资产都在这里）
> - **测试编写指南**：`testing/plan/TESTING-GUIDE.md`（新增/修改测试、E2E、回归闭环）
> - **测试工作流**：`testing/plan/TEST-WORKFLOW.md`（按改动选测试、运行节奏与耗时）
> - **验收矩阵**：`testing/acceptance/ACCEPTANCE-MATRIX.md`（需求 → 用例 → 结果）
> - **工程后续计划**：`docs/PROJECT-PLAN.md`（剩余验证、GitHub 迁移与 Actions）
> - **演示脚本**：`docs/DEMO.md`（10 分钟走完请假与报销两条链路）
> - **Python 技术栈入门**：`docs/PYTHON-FOR-SPRING-DEVS.md`
>   —— 面向熟悉 Spring Boot / .NET Core 的工程师，用 IoC / JPA / Flyway 等已有概念
>   对照 FastAPI + SQLAlchemy + Alembic，并标出 review 和调试时容易误判的地方

---

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2，Python 3.12 |
| 前端 | Vue 3 + TypeScript + Vite 6 + Ant Design Vue 4 + Pinia + Vue Router |
| 数据库 | 开发期 SQLite；目标形态 MySQL 8（切换只改连接串） |
| 认证 | JWT（PyJWT）+ bcrypt；`token_version` 支持改密/停用即时踢下线 |

---

## 快速开始

前置：Python 3.12、Node 20+（本项目在 Node 22.4 上验证）、Git Bash（Windows）。

### 一键搭建

Windows（cmd / PowerShell，不经过 WSL）：

```bat
scripts\setup.cmd
```

Git Bash / Linux / macOS：

```bash
bash scripts/setup.sh
```

幂等，可重复执行。它会创建虚拟环境、装前后端依赖、生成 `.env`、跑数据库迁移。

> macOS / Linux 上不要假定 `python` 就是 Python 3 —— 它可能是系统自带的
> Python 2.7。脚本会自己按 `python3.12` → `python3.13` → `python3.14` → `python3`
> → `python` 的顺序找可用的 3.12+，不需要手动激活什么。

> **只想先看看效果？** 用 Docker 一条命令起完整形态（MySQL + 后端 + 前端），
> 见下面的「一键部署」。它还会预置两套可直接发起的示例流程。

### 启动

Windows 开两个 cmd / PowerShell 终端（不经过 WSL）：

```bat
rem 终端 1 → http://127.0.0.1:8000
scripts\dev-backend.cmd

rem 终端 2 → http://localhost:5173
scripts\dev-frontend.cmd
```

Git Bash / Linux / macOS：

```bash
bash scripts/dev-backend.sh
bash scripts/dev-frontend.sh
```

打开 http://localhost:5173 登录。

> Windows 的 `scripts\*.cmd` 会显式找到 Git Bash 再执行对应 `.sh`。
> 在 cmd / PowerShell 里直接敲 `bash scripts\dev-backend.sh` 时，`bash` 可能
> 解析到 `C:\Windows\System32\bash.exe`（WSL），而 WSL 看不到 Windows 的
> `.venv`，会报「未找到 Python 虚拟环境」。

> 前端请用 `localhost` 而非 `127.0.0.1` —— Vite 在 Windows 上绑的是 IPv6 `::1`。

首次启动会自动创建（幂等，已存在则跳过）：

- 内置角色：平台管理员 / 设计者 / 部门主管 / 财务
- 示例部门树：总公司 → 技术部 / 产品部 / 财务部 / 人力资源部
- **示例流程库**：请假申请、费用报销（表单 + 流程都已发布，登录即可发起）
- 管理员账号：**`admin` / `admin123456`**（来自 `.env`，请登录后立即修改）
- 示例账号（**默认关闭**，见 `SEED_DEMO_ACCOUNTS`）：张三 / 李四 / 王五 / 赵六，
  统一密码 `demo123456`。打开后示例流程立刻能走完一遍 —— 但密码是公开的，
  只适合试用环境。

---

## 一键部署（Docker）

```bash
bash scripts/docker-up.sh              # 默认：内置 MySQL 8
bash scripts/docker-up.sh --postgres   # 内置 PostgreSQL 16
```

起「数据库 + 后端 + 前端（nginx）」，完成后输出访问地址与初始账号。
重复执行 = 重建镜像并滚动更新容器，数据在卷里不会丢。

| 形态 | 数据库 | 数据卷 |
|---|---|---|
| 默认 | MySQL 8 | `flowform-mysql-data` |
| `--postgres` | PostgreSQL 16 | `flowform-postgres-data` |

附件统一落在 `flowform-storage`。两种形态都只对外暴露 **8080**，数据库不映射到宿主机。

`--postgres` 会把 `DB_MODE=postgres` 写进根目录 `.env`，以后直接
`bash scripts/docker-up.sh` 也沿用；切回 MySQL 把 `.env` 里的 `DB_MODE` 清空即可。
脚本会根据 `DB_MODE` 自动叠加 `docker-compose.postgres.yml`。

手工等价操作（PostgreSQL 形态）：

```bash
cp .env.example .env                 # 至少改 JWT_SECRET
echo 'DB_MODE=postgres' >> .env
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.postgres.yml logs -f backend
docker compose -f docker-compose.yml -f docker-compose.postgres.yml down
```

MySQL 形态省掉 `DB_MODE` 和第二个 `-f`，直接 `docker compose up -d --build`。

部署后验证：

```bash
docker compose ps                         # 三个容器均为 healthy
curl -s localhost:8080/api/v1/readyz      # {"database":"postgresql"} 或 "mysql"
curl -s -o /dev/null -w '%{http_code}\n' localhost:8080/   # 200
```

要点：

- 浏览器只与 nginx 打交道：静态资源由它托管，`/api` 反代到后端容器 ——
  **同源部署，因此不需要 CORS**，也不用给前端打包时塞后端域名
- 数据库迁移在后端容器**启动时**执行（`docker-entrypoint.sh`），首次启动即建好全部表
- 切换 MySQL / PostgreSQL 不需要改代码：`DATABASE_URL` 由 compose 注入，镜像里两个驱动都装了
- 附件落在独立卷 `flowform-storage`，容器重建不丢文件
- 数据库刻意不对外暴露（compose 里没写 `ports`）；要本机连库排查再临时加
- 用 `http://局域网IP:8080` 访问也能正常登录：请求幂等键不要直接调
  `crypto.randomUUID()`，它只在 HTTPS / localhost 等安全上下文可用，在局域网
  HTTP 下是 undefined 且会在请求发出前抛错（表现为「点了没反应、DevTools 无请求」）。
  已封装在 `frontend/src/utils/requestId.ts`，生产环境仍建议上 HTTPS
- 拉镜像慢时：Docker Desktop → Settings → Resources → Proxies 填本机代理
  （如 `http://127.0.0.1:7890`）；本项目实测配置镜像加速器也可用
- 上线前请：改 `ADMIN_PASSWORD`、关掉 `SEED_DEMO_ACCOUNTS`、给 `JWT_SECRET` 一个好密钥

### 构建加速

首次构建要下依赖（pip / npm），之后不应该再慢。两个机制：

1. **分层缓存**：两个 Dockerfile 都是先 `COPY requirements.txt` / `package*.json`
   再装依赖，最后才拷源码。只改业务代码时依赖层直接命中缓存，重跑 `docker-up.sh`
   通常十几秒。
2. **BuildKit 缓存挂载**：依赖安装用 `RUN --mount=type=cache`，pip / npm 下过的包
   留在 builder 的缓存里。即使 `requirements.txt` 或 `package-lock.json` 变了，
   也只是解析变更部分，不会整包重下。缓存不进镜像，镜像体积不受影响。
3. **国内镜像源**：`docker-compose.yml` 默认把依赖源指向清华 PyPI 与 npmmirror，
   可在根目录 `.env` 覆盖（`.env.example` 里有说明）：

   ```bash
   PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
   NPM_REGISTRY=https://registry.npmmirror.com
   ```

   海外网络改成官方源：`PIP_INDEX_URL=https://pypi.org/simple`、
   `NPM_REGISTRY=https://registry.npmjs.org`。注意这只是**依赖源**；
   `python:3.12-slim` / `node:22-alpine` 等基础镜像仍从 Docker Hub 拉，
   慢的话按上一条配代理或镜像加速器。

看缓存占用 / 清理：`docker system df -v`、`docker builder prune`。
需要在多台机器间复用构建缓存时，可用 `docker buildx build --cache-to type=local,...`
把缓存导出到目录（本项目脚本未默认启用）。

---

## 脚本一览

| 脚本 | 用途 |
|---|---|
| `scripts/setup.sh` | 首次搭建（幂等） |
| `scripts/dev-backend.sh` | 启动后端，热重载。支持 `PORT=8001 bash scripts/dev-backend.sh` |
| `scripts/dev-frontend.sh` | 启动前端 Vite |
| `scripts/docker-up.sh` | 一键起完整形态（MySQL 或 PostgreSQL + 后端 + nginx 前端） |
| `scripts/check.sh` | 校验。默认全量，也可只跑受影响的一部分（见下） |
| `scripts/api.sh` | G1 API 黑盒验收（真实实现 `testing/scripts/api.sh`） |
| `scripts/e2e.sh` | 浏览器 E2E（真实实现 `testing/scripts/e2e.sh`） |
| `scripts/build-spec-pack.sh` | 生成独立验收设计用 Spec Pack |
| `scripts/migrate.sh` | Alembic 助手，缺省 = `upgrade head` |
| `scripts/_common.sh` | 公共函数，被上面各脚本 source，不单独执行 |

> Windows 上 `setup` / `dev-backend` / `dev-frontend` 另有 `scripts\*.cmd`
> 入口，cmd 与 PowerShell 都能直接运行，且不会落到 WSL。换端口：cmd 里先
> `set PORT=8001`，PowerShell 里先 `$env:PORT=8001`，再运行 `scripts\dev-backend.cmd`。

```bash
# 迁移
bash scripts/migrate.sh                                  # 升到最新
bash scripts/migrate.sh current                          # 当前版本
bash scripts/migrate.sh revision --autogenerate -m "描述" # 依模型生成
```

### 校验的范围与耗时

全量约 2.5 分钟，迭代时没必要每次都跑：

| 命令 | 覆盖 | 耗时 |
|---|---|---|
| `check.sh backend tests/test_engine_core.py` | 引擎纯核心（不碰数据库） | ~4s |
| `check.sh backend tests/test_xxx.py` | 指定测试文件 + ruff | ~10s–1min |
| `check.sh quick` | ruff + vue-tsc + vitest | ~50s |
| `check.sh backend` | 全部 pytest + ruff | ~1min |
| `check.sh frontend` | vue-tsc + vitest + build | ~1.5min |
| `check.sh` | **全量五项** | ~2.5min |

改哪里就跑哪里；**跨前后端的改动、或准备提交时跑全量**。

> pytest 默认并行（`-n auto --dist loadfile`，见 `backend/pyproject.toml`）——
> 全套 407 项从 4 分钟降到 1 分钟。单进程调试用 `pytest -n0`。

### 手工命令（不用脚本时）

脚本内部也是这么做的，只是替你处理了路径与虚拟环境。

**Windows —— 推荐直接调 venv 里的解释器，不要激活：**

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload      # 后端

cd frontend
npm run dev                                                       # 前端
```

> ⚠️ Windows 默认执行策略是 `Restricted`，`.\.venv\Scripts\Activate.ps1`
> 会被拦下并报「在此系统上禁止运行脚本」。想用激活方式的话，先执行一次
> （仅对当前用户生效，不需要管理员）：
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

**macOS / Linux：**

```bash
cd backend
source .venv/bin/activate
python -m uvicorn app.main:app --reload
```

### 各终端里的虚拟环境

| 终端 | 激活命令 | 建议 |
|---|---|---|
| Git Bash | `source .venv/Scripts/activate` | 也可不激活，直接用 `./.venv/Scripts/python.exe` |
| PowerShell | `.venv\Scripts\Activate.ps1` | **默认被执行策略拦下**，建议改用 `.\.venv\Scripts\python.exe` |
| cmd | `.venv\Scripts\activate.bat` | 可用 |

> 用 `bash scripts/*.sh` 时**不需要关心这些** —— 脚本自己找解释器，
> 且 `bash` 已被 Git for Windows 装进 PATH，PowerShell / cmd 里同样能跑。

> 用 `migrate.sh revision` 生成迁移后，**请打开 `alembic/versions/` 下的新文件核对**：
> autogenerate 不识别重命名，会误判成「删旧列 + 加新列」。

---

## 切换到 MySQL 8

默认走 SQLite（零依赖）。切到 PRD §6 的目标形态：

```bash
docker compose -f docker-compose.dev.yml up -d   # mysql8 + adminer(:8080)
```

把 `backend/.env` 的 `DATABASE_URL` 换成：

```
DATABASE_URL=mysql+pymysql://flowform:flowform123@127.0.0.1:3306/flowform?charset=utf8mb4
```

然后 `alembic upgrade head`。**不需要改任何模型或迁移代码** —— 所有列类型都走
SQLAlchemy 的可移植写法（`BigInteger().with_variant(Integer, 'sqlite')`、
`sa.JSON`、Python 侧时间戳等）。

---

## 目录结构

```
lowcode-platform/
├─ docker-compose.yml     一键部署（MySQL + 后端 + nginx 前端）
├─ docker-compose.dev.yml 只起开发用数据库（默认走 SQLite，切库时才用）
├─ scripts/               启动 / 校验 / 迁移 / 部署脚本
├─ docs/                  PRD、技术设计、引擎说明、演示脚本、Python 技术栈入门
├─ testing/               验收测试：策略、矩阵、验收用例、E2E、脚本（见 testing/README.md）
├─ backend/
│  ├─ Dockerfile          后端镜像（入口：等库 → 迁移 → uvicorn）
│  ├─ alembic/            迁移（0001 = M1 组织表，0003 = 流程表）
│  └─ app/
│     ├─ core/            配置、时间源、常量、错误、安全、授权判定
│     ├─ db/              会话与可移植列类型
│     ├─ models/          ORM 模型
│     ├─ schemas/         Pydantic DTO
│     ├─ engine/          流程引擎（纯核心 + 事务编排，见 docs/ENGINE.md）
│     ├─ services/        业务编排
│     ├─ api/v1/          路由
│     └─ seeds/           首启初始化：组织 / 示例账号 / 示例流程库
└─ frontend/
   ├─ Dockerfile          Node 构建 → nginx 托管（多阶段）
   ├─ nginx.conf          SPA 回退 + /api 反代
   └─ src/
      ├─ api/             axios 封装（token 刷新、幂等键、错误归一）
      ├─ stores/          auth / app / org
      ├─ router/          路由表与守卫
      ├─ layouts/         主框架（侧边菜单按角色过滤）
      ├─ views/           页面
      └─ components/      通用组件
```

---

## 约定

- **全链路 snake_case**（Python / JSON / TypeScript 一致）。
- 错误响应固定为 `{"detail": {"code", "message", "extra"?}}`，前端统一处理。
- 所有写操作默认弹全局提示；需要自行处理的接口传 `{ silent: true }`。
- 前端路由与 `v-permission` 只做**导航层**拦截，真正的鉴权始终在后端。

---

## 后续里程碑

| | 内容 | 交付验收 |
|---|---|---|
| M1 ✅ | 骨架、组织管理、登录鉴权、操作审计 | 可登录、可维护组织 |
| M2 ✅ | 表单模板配置器、通用表单渲染器、公式字段 | 能配出报销单表单 |
| M3 ✅ | 流程配置器、审批引擎（顺序/会签/或签/条件/抄送）+ 单测覆盖语义矩阵 | 可发布报销流程 |
| M4 ✅ | 发起中心、待办工作台、实例详情页、站内通知 | 请假流程端到端跑通 |
| M5 ✅ | 驳回重提与快照对照、运行中追加字段、值校验与级联下拉、消息中心 | 报销流程端到端跑通 |
| M6 ✅ | 示例流程库、归档检索与导出、审计打磨、Docker 部署、文档与演示 | 可交付内部试用 |
| M7 ✅ | 流程可视化画布：自动布局 + 轻编辑（节点增删、拖拽排序、分支/并行组） | 画布与清单共用流程 JSON |
| M8 ✅ | 表单栅格、分区折叠、展示控件（标题/说明/分割线/图片/富文本） | 代码与测试完成，真机验收见 E2E 报告 |
| M9 ✅ | 字段联动规则（显隐/只读/必填）与服务端兜底 | 代码与测试完成，真机验收见 E2E 报告 |
| M10 ✅ | A4 打印文档、核心路径移动端适配 | 代码与测试完成，真机验收见 E2E 报告 |
| M11 ✅ | 按角色首页：个人工作台 + 管理概览 | 首页一次取全，普通用户/管理员分角色展示 |
| M12 ✅ | 共享表格：Univer 在线 Excel，多工作簿 | 多人近实时协同、乐观锁冲突处理、导出 Excel |
| M13 ✅ | 实例业务字段检索 | 归档/我发起的可按业务字段筛选并导出 |
| M14 ✅ | 转办与委托 | 转办留痕、委托期内新任务派给被委托人 |
| M15 ✅ | AI 生成表单/流程草稿 | 默认关闭，预览确认后应用，不自动发布 |
| M16 ✅ | 三期收尾：文档、全量回归 | `bash scripts/check.sh` 五项全绿 |

> 二期设计见 `docs/PHASE2-DESIGN.md`，三期设计见 `docs/PHASE3-DESIGN.md`。
>
> Docker 形态（`docker-compose.yml` + 两个 Dockerfile）**只写完、未在本机实测过**
> —— 本机 Docker 守护进程当时没起来。首次部署请预留排查时间，欢迎反馈问题。
