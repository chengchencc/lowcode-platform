#!/usr/bin/env bash
# 启动前端开发服务器（Vite，已配置 /api 代理到后端）。
#
#   bash scripts/dev-frontend.sh

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_node

printf '\n'
info "前端开发服务器"
printf '    地址 %shttp://localhost:5173%s\n' "$C_DIM" "$C_RESET"
printf '    %s请用 localhost 而非 127.0.0.1 —— Vite 在 Windows 上绑的是 IPv6 ::1%s\n' "$C_DIM" "$C_RESET"
printf '    %sAPI 请求经 /api 代理到 http://127.0.0.1:8000%s\n' "$C_DIM" "$C_RESET"
printf '\n'

cd "$FRONTEND"
exec npm run dev
