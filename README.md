# FlowForm

面向**单组织内部**的低代码表单 + 审批流平台：业务人员自助配置表单模板与审批流程，
发起人填表提交后系统按流程自动流转，支持顺序审批、并行会签、或签、条件分支、
动态审批人、驳回重提、抄送，并按节点控制字段的可见/可编辑权限，
让表单数据随审批逐节点丰富，全程留痕可审计。

> **当前进度：M1–M6 已完成，二期 M7 已完成。** 组织管理、表单配置器、流程配置器与审批引擎、
> 发起中心与工作台、实例详情（含驳回重提 / 快照对照 / 运行中追加字段）、
> 示例流程库、归档检索与导出、操作审计全部可用；
> **PRD §9 场景一（请假）与场景二（报销）都已端到端跑通**。
> 二期 M7 增加了流程可视化画布（自动布局 + 轻编辑，与清单视图共用同一份 JSON）；
> M8 表单布局/展示控件、M9 字段联动规则、M10 打印与移动端代码已完成，待统一验收。
> 可交付内部试用 —— 部署看下面的「一键部署」，演示照着 `docs/DEMO.md` 走。
>
> - 需求：`docs/PRD-lowcode-form-approval.md`
> - 设计：`docs/TECH-DESIGN.md`（含引擎设计、API 契约、里程碑排期、**已知陷阱**）
> - **二期设计**：`docs/PHASE2-DESIGN.md`（范围、里程碑、M7–M10 技术边界）
> - **引擎代码说明**：`docs/ENGINE.md`（模块地图、一次事件的调用链、改一处跑哪个测试）
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
bash scripts/docker-up.sh          # 首次会自动生成 .env（含随机 JWT_SECRET）
```

起 MySQL 8 + 后端 + 前端（nginx），完成后输出访问地址与初始账号。
重复执行 = 重建镜像并滚动更新，数据在卷里不会丢。

手工等价操作：

```bash
cp .env.example .env               # 至少改 JWT_SECRET 与 MYSQL 密码
docker compose up -d --build       # → http://localhost:8080
docker compose logs -f backend     # 看日志
docker compose down                # 停止（加 -v 会连数据一起删）
```

要点：

- 浏览器只与 nginx 打交道：静态资源由它托管，`/api` 反代到后端容器 ——
  **同源部署，因此不需要 CORS**，也不用给前端打包时塞后端域名
- 数据库迁移在后端容器**启动时**执行（`docker-entrypoint.sh`），首次启动即建好全部表
- 附件落在独立卷 `flowform-storage`，容器重建不丢文件
- MySQL 不想对外暴露时就不暴露（compose 里没写 `ports`）；要本机连库排查再临时加
- 上线前请：改 `ADMIN_PASSWORD`、关掉 `SEED_DEMO_ACCOUNTS`、给 `JWT_SECRET` 一个好密钥

---

## 脚本一览

| 脚本 | 用途 |
|---|---|
| `scripts/setup.sh` | 首次搭建（幂等） |
| `scripts/dev-backend.sh` | 启动后端，热重载。支持 `PORT=8001 bash scripts/dev-backend.sh` |
| `scripts/dev-frontend.sh` | 启动前端 Vite |
| `scripts/docker-up.sh` | 一键起完整形态（MySQL + 后端 + nginx 前端） |
| `scripts/check.sh` | 校验。默认全量，也可只跑受影响的一部分（见下） |
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
| M8 🚧 | 表单栅格、分区折叠、展示控件（标题/说明/分割线/图片/富文本） | 代码完成，待补测试与真机验收 |
| M9 🚧 | 字段联动规则（显隐/只读/必填）与服务端兜底 | 代码完成，待补测试与真机验收 |
| M10 🚧 | A4 打印文档、核心路径移动端适配 | 代码完成，待真机验收 |

> 二期剩余里程碑（M8 表单布局/展示控件、M9 字段联动、M10 打印/移动端）见
> `docs/PHASE2-DESIGN.md`。
>
> Docker 形态（`docker-compose.yml` + 两个 Dockerfile）**只写完、未在本机实测过**
> —— 本机 Docker 守护进程当时没起来。首次部署请预留排查时间，欢迎反馈问题。
