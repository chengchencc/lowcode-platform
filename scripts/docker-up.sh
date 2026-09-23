#!/usr/bin/env bash
# 一键起完整形态：MySQL 8 + 后端 + 前端（nginx）。
#
#   bash scripts/docker-up.sh
#
# 幂等：重复执行 = 重建镜像并滚动更新容器，数据在卷里不会丢。
# 首次执行会：补 .env（并生成随机 JWT_SECRET）→ 构建镜像 → 起容器 → 等健康检查。

source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

COMPOSE="docker compose"
ENV_FILE="$ROOT/.env"

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

# JWT_SECRET 留空会让 compose 直接拒绝启动（这是故意的：默认密钥上线等于没有认证）。
# 但「一键起」不该卡在让用户自己去 openssl —— 这里直接生成一个写回去。
if ! grep -qE '^JWT_SECRET=.+$' "$ENV_FILE"; then
  secret="$(generate_secret)"
  # 用 # 作分隔符：密钥里可能出现 / 与 &，用 / 会破坏 sed 的替换
  sed -i.bak "s#^JWT_SECRET=.*#JWT_SECRET=${secret}#" "$ENV_FILE" && rm -f "$ENV_FILE.bak"
  ok "已生成随机 JWT_SECRET 写入 .env"
fi

# ---- 构建与启动 ----

info "构建镜像（首次较慢，之后走缓存）"
$COMPOSE build

info "启动容器"
$COMPOSE up -d

# ---- 等健康 ----

WEB_PORT="$(sed -n 's/^WEB_PORT=\(.*\)$/\1/p' "$ENV_FILE" | head -1)"
WEB_PORT="${WEB_PORT:-8080}"

info "等待前端就绪（最多 60 秒）"
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
else
  warn "前端还没起来。看看日志： $COMPOSE logs -f frontend backend"
fi

ADMIN_USER="$(sed -n 's/^ADMIN_USERNAME=\(.*\)$/\1/p' "$ENV_FILE" | head -1)"
ADMIN_PASS="$(sed -n 's/^ADMIN_PASSWORD=\(.*\)$/\1/p' "$ENV_FILE" | head -1)"
printf '  登录：%s / %s\n' "${ADMIN_USER:-admin}" "${ADMIN_PASS:-admin123456}"
printf '  %s首次登录后请立刻改密。停止：docker compose down（加 -v 会连数据一起删）%s\n' \
  "$C_DIM" "$C_RESET"
