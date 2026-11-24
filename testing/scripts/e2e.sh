#!/usr/bin/env bash
# 一键跑浏览器 E2E：重置独立库 → 起后端 + 前端 → 跑 Playwright。
#
#   bash scripts/e2e.sh                  # 全量（无头）
#   bash scripts/e2e.sh --headed         # 打开真实浏览器，逐步可见
#   bash scripts/e2e.sh @p0 --headed     # 只跑 @p0 且可见
#   bash scripts/e2e.sh --ui             # Playwright 交互式 UI
#   bash scripts/e2e.sh --no-reset       # 保留 testing/.runtime/e2e 数据
#   bash scripts/e2e.sh --no-server      # 复用已启动的服务
#
# 这是真实实现；仓库根部的 scripts/e2e.sh 是兼容入口。
# 前置：cd testing/e2e && npm install

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../scripts/_common.sh"
source "$SCRIPT_DIR/e2e-env.sh"

require_venv
require_node

NO_RESET=0
NO_SERVER=0
UI=0
HEADED=0
ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-reset)  NO_RESET=1 ;;
    --no-server) NO_SERVER=1 ;;
    --ui)        UI=1 ;;
    --headed)    HEADED=1 ;;
    --)          shift; ARGS+=("$@"); break ;;
    *)           ARGS+=("$1") ;;
  esac
  shift
done

if [ ! -d "$ROOT/testing/e2e/node_modules/@playwright/test" ]; then
  fail "E2E 依赖未安装：testing/e2e/node_modules"
  printf '  请先执行：\n' >&2
  printf '    cd testing/e2e && npm install\n' >&2
  exit 1
fi

if [ "$NO_RESET" = 0 ]; then
  bash "$ROOT/testing/scripts/e2e-reset.sh"
fi

http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -sf --max-time 2 "$url" >/dev/null 2>&1
  else
    "$VENV_PY" - "$url" <<'PY' >/dev/null 2>&1
import sys
import urllib.request
urllib.request.urlopen(sys.argv[1], timeout=2)
PY
  fi
}

wait_for() {
  local url="$1" name="$2" pid="$3" log="$4" i
  for i in $(seq 1 120); do
    if http_ok "$url"; then
      ok "$name 已就绪"
      return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      fail "$name 启动失败，日志：$log"
      tail -n 40 "$log" >&2 || true
      return 1
    fi
    sleep 0.5
  done
  fail "$name 启动超时（60s），日志：$log"
  tail -n 40 "$log" >&2 || true
  return 1
}

kill_tree() {
  local pid="${1:-}"
  [ -n "$pid" ] || return 0
  if [ "$IS_WINDOWS" = 1 ] && command -v taskkill >/dev/null 2>&1; then
    MSYS_NO_PATHCONV=1 taskkill /F /T /PID "$pid" >/dev/null 2>&1 || true
  else
    kill "$pid" >/dev/null 2>&1 || true
  fi
}

# Windows 上后台进程的 PID 关系不一定可靠（npm / vite 会再起子进程），
# 清理时再按监听端口兜底杀一次，避免下次 reset 时数据库被占用。
kill_port() {
  local port="$1" pid
  pid="$(port_holder "$port")"
  [ -n "$pid" ] && kill_tree "$pid"
}

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  kill_tree "$FRONTEND_PID"
  kill_tree "$BACKEND_PID"
  if [ "$IS_WINDOWS" = 1 ]; then
    kill_port "$E2E_FRONTEND_PORT"
    kill_port "$E2E_BACKEND_PORT"
  fi
}
trap cleanup EXIT INT TERM

if [ "$NO_SERVER" = 0 ]; then
  require_free_port "$E2E_BACKEND_PORT"
  require_free_port "$E2E_FRONTEND_PORT"
  mkdir -p "$E2E_DIR"

  info "启动后端 http://127.0.0.1:$E2E_BACKEND_PORT"
  (
    cd "$BACKEND"
    exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$E2E_BACKEND_PORT"
  ) > "$E2E_DIR/backend.log" 2>&1 &
  BACKEND_PID=$!

  info "启动前端 http://localhost:$E2E_FRONTEND_PORT"
  (
    cd "$FRONTEND"
    exec npm run dev -- --port "$E2E_FRONTEND_PORT" --strictPort
  ) > "$E2E_DIR/frontend.log" 2>&1 &
  FRONTEND_PID=$!

  wait_for "http://127.0.0.1:$E2E_BACKEND_PORT/api/v1/readyz" "后端" "$BACKEND_PID" "$E2E_DIR/backend.log"
  wait_for "http://localhost:$E2E_FRONTEND_PORT/" "前端" "$FRONTEND_PID" "$E2E_DIR/frontend.log"
fi

PLAY_ARGS=()
for arg in "${ARGS[@]+"${ARGS[@]}"}"; do
  case "$arg" in
    @*) PLAY_ARGS+=("--grep" "$arg") ;;
    *)  PLAY_ARGS+=("$arg") ;;
  esac
done

printf '\n'
info "运行 Playwright（${E2E_BASE_URL}）"
rc=0
cd "$ROOT/testing/e2e"
if [ "$UI" = 1 ]; then
  if [ ${#PLAY_ARGS[@]} -gt 0 ]; then
    npm run test:ui -- "${PLAY_ARGS[@]}" || rc=$?
  else
    npm run test:ui || rc=$?
  fi
elif [ "$HEADED" = 1 ]; then
  if [ ${#PLAY_ARGS[@]} -gt 0 ]; then
    npm run test:headed -- "${PLAY_ARGS[@]}" || rc=$?
  else
    npm run test:headed || rc=$?
  fi
else
  if [ ${#PLAY_ARGS[@]} -gt 0 ]; then
    npm test -- "${PLAY_ARGS[@]}" || rc=$?
  else
    npm test || rc=$?
  fi
fi

exit "$rc"
