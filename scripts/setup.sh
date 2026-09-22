#!/usr/bin/env bash
# 首次搭建：虚拟环境 + 依赖 + .env + 数据库迁移 + 前端依赖。
#
#   bash scripts/setup.sh
#
# 幂等：已存在的步骤会跳过，可以放心重复执行。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

# ---- 后端 ----
if ! command -v python >/dev/null 2>&1; then
  fail "未找到 python，请先安装 Python 3.12"
  exit 1
fi

info "后端：创建虚拟环境"
if [ -d "$BACKEND/.venv" ]; then
  ok "已存在，跳过"
else
  python -m venv "$BACKEND/.venv"
  ok "已创建 $BACKEND/.venv"
fi

require_venv

info "后端：安装依赖"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r "$BACKEND/requirements-dev.txt"
ok "依赖已安装"

info "后端：准备 .env"
ensure_env_file

info "后端：执行数据库迁移"
(cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head >/dev/null)
ok "迁移完成（数据库类型：$(database_kind)）"

# ---- 前端 ----
if ! command -v npm >/dev/null 2>&1; then
  warn "未找到 npm，跳过前端依赖安装（请安装 Node.js 20+ 后重跑本脚本）"
  exit 0
fi

info "前端：安装依赖"
(cd "$FRONTEND" && npm install --no-audit --no-fund)
ok "依赖已安装"

# ---- 完成 ----
printf '\n'
ok "搭建完成。启动方式："
printf '    %s终端 1%s  bash scripts/dev-backend.sh\n' "$C_DIM" "$C_RESET"
printf '    %s终端 2%s  bash scripts/dev-frontend.sh\n' "$C_DIM" "$C_RESET"
printf '\n'
printf '  前端    http://localhost:5173\n'
printf '  API 文档 http://127.0.0.1:8000/docs\n'
printf '  账号    admin / admin123456 %s（请登录后立即修改）%s\n' "$C_DIM" "$C_RESET"
