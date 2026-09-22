#!/usr/bin/env bash
# 公共工具函数。由其他脚本 source，不作为入口执行。
#
# 用法：
#   source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# ---- 输出 ----
if [ -t 1 ]; then
  C_DIM=$'\033[2m'; C_RED=$'\033[31m'; C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'; C_BLUE=$'\033[34m'; C_RESET=$'\033[0m'
else
  C_DIM=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''; C_RESET=''
fi

info()  { printf '%s==>%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok()    { printf '%s ✓ %s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn()  { printf '%s ! %s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
fail()  { printf '%s ✗ %s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }

# ---- 虚拟环境 ----
# Git Bash / Windows 是 .venv/Scripts，Linux / macOS 是 .venv/bin
VENV_PY=""

resolve_venv_py() {
  if [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then
    VENV_PY="$BACKEND/.venv/Scripts/python.exe"
  elif [ -x "$BACKEND/.venv/bin/python" ]; then
    VENV_PY="$BACKEND/.venv/bin/python"
  else
    VENV_PY=""
  fi
}

require_venv() {
  resolve_venv_py
  if [ -z "$VENV_PY" ]; then
    fail "未找到 Python 虚拟环境：$BACKEND/.venv"
    printf '  请先执行：bash scripts/setup.sh\n' >&2
    exit 1
  fi
}

# ---- Node ----
require_node() {
  if ! command -v npm >/dev/null 2>&1; then
    fail "未找到 npm，请先安装 Node.js 20 或更高版本"
    exit 1
  fi
  if [ ! -d "$FRONTEND/node_modules" ]; then
    fail "前端依赖未安装：$FRONTEND/node_modules"
    printf '  请先执行：bash scripts/setup.sh\n' >&2
    exit 1
  fi
}

# ---- 配置 ----
# 只回显数据库类型（sqlite/mysql），不打印可能含密码的连接串
database_kind() {
  local env_file="$BACKEND/.env"
  [ -f "$env_file" ] || { printf '未配置'; return; }
  local url
  url="$(sed -n 's/^DATABASE_URL=\(.*\)$/\1/p' "$env_file" | head -1)"
  case "$url" in
    sqlite*) printf 'sqlite' ;;
    mysql*)  printf 'mysql' ;;
    '')      printf '未配置' ;;
    *)       printf '未知' ;;
  esac
}

ensure_env_file() {
  if [ ! -f "$BACKEND/.env" ]; then
    warn "backend/.env 不存在，正在从 .env.example 复制"
    cp "$BACKEND/.env.example" "$BACKEND/.env"
    ok "已生成 backend/.env（生产环境请修改 JWT_SECRET）"
  fi
}
