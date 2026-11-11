#!/usr/bin/env bash
# 一键起完整形态：数据库 + 后端 + 前端（nginx）。
#
#   bash scripts/docker-up.sh              # 默认：内置 MySQL 8
#   bash scripts/docker-up.sh --postgres   # 内置 PostgreSQL 16
#
# 数据都在命名卷里：MySQL 是 flowform-mysql-data，PostgreSQL 是
# flowform-postgres-data，附件是 flowform-storage。
#
# 幂等：重复执行 = 重建镜像并滚动更新容器，数据在卷里不会丢。
# 首次执行会：补 .env（并生成随机 JWT_SECRET）→ 构建镜像 → 起容器 → 等健康检查。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

ENV_FILE="$ROOT/.env"
PG_OVERLAY="$ROOT/docker-compose.postgres.yml"

# ---- 参数 ----
WANT_POSTGRES=0
for arg in "$@"; do
  case "$arg" in
    --postgres|--pg) WANT_POSTGRES=1 ;;
    -h|--help)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      fail "未知参数：$arg"
      printf '  用法：bash scripts/docker-up.sh [--postgres]\n' >&2
      exit 2
      ;;
  esac
done

# ---- 前置检查 ----

if ! command -v docker >/dev/null 2>&1; then
  fail "未找到 docker，请先安装 Docker Desktop"
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  fail "Docker 未运行（或当前用户没有权限）"
  printf '  请先启动 Docker Desktop，再重试\n' >&2
  exit 1
fi

# ---- .env ----

if [ ! -f "$ENV_FILE" ]; then
  info "未找到 .env，从 .env.example 生成"
  cp "$ROOT/.env.example" "$ENV_FILE"
fi

# 只读 .env 里的值，不 source（值里可能有空格 / 特殊字符）
read_env() { sed -n "s/^$1=\(.*\)$/\1/p" "$ENV_FILE" | head -1; }

# JWT_SECRET 留空会让 compose 直接拒绝启动（这是故意的：默认密钥上线等于没有认证）。
# 但「一键起」不该卡在让用户自己去 openssl —— 这里直接生成一个写回去。
if ! grep -qE '^JWT_SECRET=.+$' "$ENV_FILE"; then
  secret="$(generate_secret)"
  # 用 # 作分隔符：密钥里可能出现 / 与 &，用 / 会破坏 sed 的替换
  sed -i.bak "s#^JWT_SECRET=.*#JWT_SECRET=${secret}#" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  ok "已生成随机 JWT_SECRET 写入 .env"
fi

# ---- 数据库形态 ----

if [ "$WANT_POSTGRES" = 1 ]; then
  if [ "$(read_env DB_MODE)" != "postgres" ]; then
    # 记下来，下次直接 bash scripts/docker-up.sh 也还是 PostgreSQL
    if grep -qE '^DB_MODE=' "$ENV_FILE"; then
      sed -i.bak 's#^DB_MODE=.*#DB_MODE=postgres#' "$ENV_FILE" && rm -f "$ENV_FILE.bak"
    else
      printf '\nDB_MODE=postgres\n' >> "$ENV_FILE"
    fi
    ok "已在 .env 记录 DB_MODE=postgres"
  fi
fi

case "$(read_env DB_MODE)" in
  postgres|postgresql|pg) DB_MODE=postgres ;;
  ''|mysql)               DB_MODE=mysql ;;
  *)
    fail "不支持的 DB_MODE：$(read_env DB_MODE)"
    printf '  可用：留空 / mysql / postgres\n' >&2
    exit 1
    ;;
esac

COMPOSE=(docker compose -f "$ROOT/docker-compose.yml")
COMPOSE_HINT="docker compose"

if [ "$DB_MODE" = postgres ]; then
  if [ ! -f "$PG_OVERLAY" ]; then
    fail "缺少覆盖文件：$PG_OVERLAY"
    exit 1
  fi
  COMPOSE+=(-f "$PG_OVERLAY")
  COMPOSE_HINT="docker compose -f docker-compose.yml -f docker-compose.postgres.yml"
  info "数据库：PostgreSQL 16（容器内置）"
else
  info "数据库：MySQL 8（容器内置）"
fi

# ---- 构建与启动 ----

info "构建镜像（首次较慢，之后走缓存）"
"${COMPOSE[@]}" build

info "启动容器"
"${COMPOSE[@]}" up -d

# ---- 等健康 ----

WEB_PORT="$(read_env WEB_PORT)"
WEB_PORT="${WEB_PORT:-8080}"

info "等待服务就绪（最多 60 秒）"
ready=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${WEB_PORT}/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

echo
if [ "$ready" = "1" ]; then
  ok "已就绪 → http://localhost:${WEB_PORT}"
  api_json="$(curl -fsS "http://127.0.0.1:${WEB_PORT}/api/v1/readyz" 2>/dev/null || true)"
  db_kind="$(printf '%s' "$api_json" | sed -n 's/.*"database":"\([^"]*\)".*/\1/p')"
  [ -n "$db_kind" ] && printf '  数据库连通性：%s\n' "$db_kind"
else
  warn "服务还没起来。看看日志： $COMPOSE_HINT logs -f backend frontend"
  printf '  %s提示：%s ps 可看各容器健康状态%s\n' "$C_DIM" "$COMPOSE_HINT" "$C_RESET" >&2
fi

ADMIN_USER="$(read_env ADMIN_USERNAME)"
ADMIN_PASS="$(read_env ADMIN_PASSWORD)"
printf '  部署形态：%s\n' "$DB_MODE"
printf '  登录：%s / %s\n' "${ADMIN_USER:-admin}" "${ADMIN_PASS:-admin123456}"
printf '  %s首次登录后请立刻改密。停止：%s down（加 -v 会连数据一起删）%s\n' \
  "$C_DIM" "$COMPOSE_HINT" "$C_RESET"
