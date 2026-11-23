# 内网 / 离线部署镜像包

> 更新：2026-11-20
> 场景：UAT 为内网 CentOS，无法访问 Docker Hub / pypi / npm。
> 当前已下载基础镜像；应用镜像需要在一台有 Docker 的联网机器上构建后一并导出。

## 1. 已准备好的基础镜像

目录：`testing/.runtime/offline-images/`（gitignore，不提交；约 1.4 GB）

| 文件 | 镜像 | 用途 |
|---|---|---|
| `mysql_8.0.tar` | `mysql:8.0` | MySQL 部署 |
| `postgres_16-alpine.tar` | `postgres:16-alpine` | PostgreSQL 部署（可选） |
| `python_3.12-slim.tar` | `python:3.12-slim` | 后端镜像构建基础 |
| `node_22-alpine.tar` | `node:22-alpine` | 前端镜像构建基础 |
| `nginx-1.27-alpine.tar` | `nginx:1.27-alpine` | 前端运行镜像基础 |

均为 `linux/amd64`（CentOS x86_64 可直接用），格式为 `docker load` 可识别的 Docker archive。

## 2. 在 UAT 机器上导入

```bash
mkdir -p /opt/flowform/images
# 把 5 个 tar 拷到该目录后：
cd /opt/flowform/images
for f in *.tar; do docker load -i "$f"; done

docker images | grep -E 'mysql|postgres|python|node|nginx'
```

## 3. 应用镜像（backend / frontend）

当前本机 Docker 守护进程不可用，**应用镜像尚未构建**。两种方式任选：

### 方式 A：联网机器构建后整体导出（推荐，UAT 完全离线）

在一台能联网、能运行 Docker 的机器上：

```bash
git clone <repo> && cd lowcode-platform
cp .env.example .env        # 至少设置 JWT_SECRET 与数据库密码
docker compose build

# 查看 compose 生成的镜像名（通常是 <目录名>-backend / <目录名>-frontend）
docker compose config --images

docker save \
  lowcode-platform-backend:latest \
  lowcode-platform-frontend:latest \
  mysql:8.0 postgres:16-alpine python:3.12-slim node:22-alpine nginx:1.27-alpine \
  -o flowform-all-images.tar
```

把 `flowform-all-images.tar` 拷到 UAT：

```bash
docker load -i flowform-all-images.tar
```

如果 UAT 只跑 MySQL，可以去掉 postgres 镜像。

### 方式 B：UAT 上构建，依赖走内网镜像源

基础镜像已具备，若内网有 PyPI / npm 镜像，可在 `.env` 配置：

```dotenv
PIP_INDEX_URL=https://<内网 PyPI>/simple
NPM_REGISTRY=https://<内网 npm>
```

然后：

```bash
docker compose up -d --build
```

> 注意：`.env.example` 默认写的是国内公网镜像；内网必须替换成可达地址，否则构建仍会卡在依赖下载。

## 4. 启动与验证

MySQL：

```bash
docker compose up -d
docker compose ps                     # mysql/backend/frontend 均为 healthy
curl -fsS http://127.0.0.1:8080/api/v1/readyz
```

PostgreSQL：

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d
```

首次启动后端会执行迁移与种子；日志出现 `Uvicorn running` 且 `/readyz` 返回 200 即就绪。

## 5. 待办

- [ ] 在本机或联网构建机执行一次方式 A，生成 `flowform-all-images.tar` 并校验 `docker load`。
- [ ] 在 CentOS UAT 上完成一次全新部署、重启持久化、附件卷验证（ENV-01）。
- [ ] PostgreSQL 形态同样验证一次（ENV-02）。
