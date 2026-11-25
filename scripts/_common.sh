#!/usr/bin/env bash
# 公共工具函数。由其他脚本 source，不作为入口执行。
#
# 用法：
#   source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# ---- 平台 ----
# MSYS / MinGW = Git Bash（Windows）。提示里据此给出 Windows 原生入口，
# 免得用户回到 cmd / PowerShell 里又敲 `bash ...` 被 WSL 接管。
case "$(uname -s 2>/dev/null)" in
  MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 ;;
  *)                    IS_WINDOWS=0 ;;
esac

# ---- Python ----
# 解释器名跨平台不一致：Windows 上 `python` 就是 Python 3；macOS / Linux 上
# `python` 往往是系统自带的 Python 2.7（没有 venv 模块），甚至根本不存在，
# Python 3 叫 `python3`。所以不硬编码名字，按「离 3.12 最近」的顺序探测。
SYSTEM_PY=""

_python_version_ok() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
    >/dev/null 2>&1
}

# 找到可用的 Python 3.12+ 时设置 SYSTEM_PY，否则保持为空
find_python() {
  if [ -n "$SYSTEM_PY" ]; then
    return 0
  fi
  local candidate
  for candidate in python3.12 python3.13 python3.14 python3 python; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    if _python_version_ok "$candidate"; then
      SYSTEM_PY="$(command -v "$candidate")"
      return 0
    fi
  done
  return 0
}

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

# 找到本机可执行的虚拟环境解释器时返回 0，否则返回 1 并清空 VENV_PY
resolve_venv_py() {
  if [ -x "$BACKEND/.venv/Scripts/python.exe" ]; then
    VENV_PY="$BACKEND/.venv/Scripts/python.exe"
  elif [ -x "$BACKEND/.venv/bin/python" ]; then
    VENV_PY="$BACKEND/.venv/bin/python"
  else
    VENV_PY=""
    return 1
  fi
  return 0
}

require_venv() {
  # resolve_venv_py 找不到时返回 1；这里必须吞掉，否则 set -e 会直接退出，
  # 用户看不到下面的提示。
  resolve_venv_py || true
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
# 只回显数据库类型（sqlite/postgresql/mysql），不打印可能含密码的连接串
database_kind() {
  local env_file="$BACKEND/.env"
  [ -f "$env_file" ] || { printf '未配置'; return; }
  local url
  url="$(sed -n 's/^DATABASE_URL=\(.*\)$/\1/p' "$env_file" | head -1)"
  case "$url" in
    sqlite*)     printf 'sqlite' ;;
    postgres*)   printf 'postgresql' ;;
    mysql*)      printf 'mysql' ;;
    '')          printf '未配置' ;;
    *)           printf '未知' ;;
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
  # 尽力找出占用端口的进程，找不到就返回空。
  # netstat 的参数各平台不兼容（Windows -ano / macOS 没有 -o 的同样语义），
  # 所以按平台选工具。
  local port="$1" pid=""
  if [ "$IS_WINDOWS" = 1 ] && command -v netstat >/dev/null 2>&1; then
    pid="$(netstat -ano 2>/dev/null | grep -E "[:.]${port}[[:space:]]" | grep -i listening | head -1 | awk '{print $NF}')"
    [ "$pid" = "0" ] && pid=""
  elif command -v lsof >/dev/null 2>&1; then
    # macOS / 多数 Linux 发行版
    pid="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)"
  elif command -v ss >/dev/null 2>&1; then
    pid="$(ss -ltnp 2>/dev/null | grep -E "[:.]${port}[[:space:]]" | head -1 | sed -n 's/.*pid=\([0-9]*\).*/\1/p')"
  fi
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    printf '%s' "$pid"
  fi
  return 0
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
      if [ "$IS_WINDOWS" = 1 ]; then
        printf '    Windows:  taskkill /F /PID %s\n' "$pid" >&2
        printf '    Git Bash: powershell -Command "Stop-Process -Id %s -Force"\n' "$pid" >&2
      else
        printf '    结束进程: kill %s\n' "$pid" >&2
      fi
    fi
    if [ "$IS_WINDOWS" = 1 ]; then
      printf '    也可以换端口启动：set PORT=8001 ^&^& scripts\\dev-backend.cmd\n' >&2
    else
      printf '    也可以换端口启动：PORT=8001 bash scripts/dev-backend.sh\n' >&2
    fi
    printf '\n' >&2
    printf '    %s提示：之前用 Ctrl+C 之外的方式关掉后端（或直接关终端）时，' "$C_DIM" >&2
    printf '进程可能残留。%s\n' "$C_RESET" >&2
    exit 1
  fi
}
