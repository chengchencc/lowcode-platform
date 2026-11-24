#!/usr/bin/env bash
# 运行 G1 API 黑盒验收：重置 E2E 独立库 → 起后端 → pytest → 停后端。
#
#   bash scripts/api.sh                 # 全量 API 黑盒
#   bash scripts/api.sh test_auth.py    # 只跑某个文件（pytest 参数透传）
#   bash scripts/api.sh -k hidden       # 只跑匹配的用例
#   bash scripts/api.sh --no-reset      # 保留 testing/.runtime/e2e 数据
#   bash scripts/api.sh --no-server     # 复用已启动的 8000 服务（不重置库）
#
# API 测试只走 HTTP，不 import backend 业务实现。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../scripts/_common.sh"
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/e2e-env.sh"

require_venv

API_PORT="${API_PORT:-8000}"
export API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:$API_PORT/api/v1}"
NO_RESET=0
NO_SERVER=0
ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-reset)  NO_RESET=1 ;;
    --no-server) NO_SERVER=1; NO_RESET=1 ;;
    --)          shift; ARGS+=("$@"); break ;;
    *)           ARGS+=("$1") ;;
  esac
  shift
done

kill_tree() {
  local pid="${1:-}"
  [ -n "$pid" ] || return 0
  if [ "$IS_WINDOWS" = 1 ] && command -v taskkill >/dev/null 2>&1; then
    MSYS_NO_PATHCONV=1 taskkill /F /T /PID "$pid" >/dev/null 2>&1 || true
  else
    kill "$pid" >/dev/null 2>&1 || true
  fi
}

kill_port() {
  local port="$1" pid
  pid="$(port_holder "$port")"
  [ -n "$pid" ] && kill_tree "$pid"
}

http_ok() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -sf --max-time 2 "$url" >/dev/null 2>&1
  else
    "$VENV_PY" - "$url" <<'PY' >/dev/null 2>&1
import sys, urllib.request
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

if [ "$NO_RESET" = 0 ]; then
  bash "$ROOT/testing/scripts/e2e-reset.sh"
fi

BACKEND_PID=""
cleanup() {
  kill_tree "$BACKEND_PID"
  if [ "$IS_WINDOWS" = 1 ]; then
    kill_port "$API_PORT"
  fi
}
trap cleanup EXIT INT TERM

if [ "$NO_SERVER" = 0 ]; then
  require_free_port "$API_PORT"
  mkdir -p "$E2E_DIR"
  info "启动后端 http://127.0.0.1:$API_PORT"
  (
    cd "$BACKEND"
    exec "$VENV_PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
  ) > "$E2E_DIR/api-backend.log" 2>&1 &
  BACKEND_PID=$!
  wait_for "http://127.0.0.1:$API_PORT/api/v1/readyz" "后端" "$BACKEND_PID" "$E2E_DIR/api-backend.log"
fi

printf '\n'
info "运行 API 黑盒验收（${API_BASE_URL}）"
rc=0
if [ ${#ARGS[@]} -gt 0 ]; then
  "$VENV_PY" -m pytest testing/api "${ARGS[@]}" || rc=$?
else
  "$VENV_PY" -m pytest testing/api || rc=$?
fi

exit "$rc"
