# FlowForm

面向**单组织内部**的低代码表单 + 审批流平台：业务人员自助配置表单模板与审批流程，
发起人填表提交后系统按流程自动流转，支持顺序审批、并行会签、或签、条件分支、
动态审批人、驳回重提、抄送，并按节点控制字段的可见/可编辑权限，
让表单数据随审批逐节点丰富，全程留痕可审计。

> **当前进度：M1（骨架与组织）已完成。** 登录鉴权、用户 / 部门 / 角色管理、
> 操作审计已可用；表单配置器与审批引擎在 M2–M6 实现。
>
> - 需求：`docs/PRD-lowcode-form-approval.md`
> - 设计：`docs/TECH-DESIGN.md`（含引擎设计、API 契约、里程碑排期、**已知陷阱**）

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

```bash
bash scripts/setup.sh
```

幂等，可重复执行。它会创建虚拟环境、装前后端依赖、生成 `.env`、跑数据库迁移。

### 启动

开两个终端：

```bash
bash scripts/dev-backend.sh     # 终端 1 → http://127.0.0.1:8000
bash scripts/dev-frontend.sh    # 终端 2 → http://localhost:5173
```

打开 http://localhost:5173 登录。

> 前端请用 `localhost` 而非 `127.0.0.1` —— Vite 在 Windows 上绑的是 IPv6 `::1`。

首次启动会自动创建（幂等，已存在则跳过）：

- 内置角色：平台管理员 / 设计者 / 部门主管 / 财务
- 示例部门树：总公司 → 技术部 / 产品部 / 财务部 / 人力资源部
- 管理员账号：**`admin` / `admin123456`**（来自 `.env`，请登录后立即修改）

---

## 脚本一览

| 脚本 | 用途 |
|---|---|
| `scripts/setup.sh` | 首次搭建（幂等） |
| `scripts/dev-backend.sh` | 启动后端，热重载。支持 `PORT=8001 bash scripts/dev-backend.sh` |
| `scripts/dev-frontend.sh` | 启动前端 Vite |
| `scripts/check.sh` | 全套校验：pytest + ruff + vue-tsc + vite build，逐项汇总 |
| `scripts/migrate.sh` | Alembic 助手，缺省 = `upgrade head` |
| `scripts/_common.sh` | 公共函数，被上面各脚本 source，不单独执行 |

```bash
# 若不想用脚本，等价的手工命令：
cd backend && source .venv/Scripts/activate
python -m uvicorn app.main:app --reload     # 后端
cd frontend && npm run dev                   # 前端

# 迁移
bash scripts/migrate.sh                                  # 升到最新
bash scripts/migrate.sh current                          # 当前版本
bash scripts/migrate.sh revision --autogenerate -m "描述" # 依模型生成
```

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
├─ scripts/               启动 / 校验 / 迁移脚本
├─ docs/                  PRD 与技术设计
├─ backend/
│  ├─ alembic/            迁移（0001 = M1 组织表）
│  └─ app/
│     ├─ core/            配置、时间源、常量、错误、安全、授权判定
│     ├─ db/              会话与可移植列类型
│     ├─ models/          ORM 模型
│     ├─ schemas/         Pydantic DTO
│     ├─ services/        业务编排
│     ├─ api/v1/          路由
│     └─ seeds/           首启初始化种子
└─ frontend/
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
| M2 | 表单模板配置器、通用表单渲染器、公式字段 | 能配出报销单表单 |
| M3 | 流程配置器、审批引擎（顺序/会签/或签/条件/抄送）+ 单测覆盖语义矩阵 | 可发布报销流程 |
| M4 | 发起中心、待办工作台、实例详情页、站内通知 | 请假流程端到端跑通 |
| M5 | 驳回重提、运行中追加字段、公式与级联下拉 | 报销流程端到端跑通 |
| M6 | 示例流程库、归档导出、Docker 部署、文档 | 可交付内部试用 |
