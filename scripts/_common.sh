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

# ---- 密钥 ----

# 生成随机密钥（JWT_SECRET 用）。openssl 在 Git Bash 里有，但精简的
# Linux 发行版常常没装，所以逐级回退到 python3 / /dev/urandom。
generate_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c 'import secrets; print(secrets.token_hex(32))'
  else
    head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'
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

# ---- 端口 ----

#: 端口被占用时 Windows 报的是 WinError 10013（"以一种访问权限不允许的方式做了
#: 一个访问套接字的尝试"），Linux 报 "Address already in use"。前者完全看不出
#: 是端口问题，所以启动前先自己检查一次，给出可操作的提示。
port_holder() {
  # 尽力找出占用端口的进程，找不到就返回空
  local port="$1" pid
  if command -v netstat >/dev/null 2>&1; then
    pid="$(netstat -ano 2>/dev/null | grep -E "[:.]${port}[[:space:]]" | grep -i listening | head -1 | awk '{print $NF}')"
    [ -n "$pid" ] && [ "$pid" != "0" ] && printf '%s' "$pid"
  fi
}

require_free_port() {
  local port="$1"
  if ! "$VENV_PY" - "$port" <<'PY' 2>/dev/null
import socket, sys
sock = socket.socket()
sock.settimeout(0.6)
try:
    # 连得上就说明有人在监听 —— 比 bind 探测更可靠（不受 SO_REUSEADDR 影响）
    listening = sock.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0
finally:
    sock.close()
sys.exit(1 if listening else 0)
PY
  then
    local pid; pid="$(port_holder "$port")"
    fail "端口 $port 已被占用，无法启动后端。"
    if [ -n "$pid" ]; then
      printf '    占用进程 PID: %s\n' "$pid" >&2
      printf '    Windows:  taskkill /F /PID %s\n' "$pid" >&2
      printf '    Git Bash: powershell -Command "Stop-Process -Id %s -Force"\n' "$pid" >&2
    fi
    printf '    也可以换端口启动：PORT=8001 bash scripts/dev-backend.sh\n' >&2
    printf '\n' >&2
    printf '    %s提示：之前用 Ctrl+C 之外的方式关掉后端（或直接关终端）时，' "$C_DIM" >&2
    printf '进程可能残留。%s\n' "$C_RESET" >&2
    exit 1
  fi
}
