#!/usr/bin/env bash
# 启动后端开发服务器（热重载）。
#
#   bash scripts/dev-backend.sh
#   PORT=8001 bash scripts/dev-backend.sh     # 换端口
#
# 不依赖 shell 里已激活的虚拟环境，直接用 .venv 里的解释器。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_venv
ensure_env_file

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

# 先自己检查端口，避免直接抛 WinError 10013 / EADDRINUSE
require_free_port "$PORT"

printf '\n'
info "后端开发服务器"
printf '    地址     %shttp://%s:%s%s\n' "$C_DIM" "$HOST" "$PORT" "$C_RESET"
printf '    API 文档 %shttp://%s:%s/docs%s\n' "$C_DIM" "$HOST" "$PORT" "$C_RESET"
printf '    数据库   %s\n' "$(database_kind)"
printf '\n'

cd "$BACKEND"
exec "$VENV_PY" -m uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
