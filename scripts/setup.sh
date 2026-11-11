#!/usr/bin/env bash
# 首次搭建：虚拟环境 + 依赖 + .env + 数据库迁移 + 前端依赖。
#
#   bash scripts/setup.sh
#
# 幂等：已存在的步骤会跳过，可以放心重复执行。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

# ---- 后端 ----
# 不假定命令叫 `python`：macOS 上它可能是系统自带的 Python 2.7（没有 venv），
# Windows 上才是 Python 3。见 _common.sh 的 find_python。
find_python
if [ -z "$SYSTEM_PY" ]; then
  fail "未找到 Python 3.12 或更高版本"
  printf '  安装：https://www.python.org/downloads/ （或 brew install python@3.12）\n' >&2
  printf '  已安装但没被找到？在终端执行 python3 --version 自查。\n' >&2
  exit 1
fi
# 变量后面紧跟全角标点时必须加花括号：macOS 自带的 bash 3.2 会把多字节字符
# 当成变量名的一部分，报 "SYSTEM_PY<乱码>: unbound variable"。
info "使用 $("$SYSTEM_PY" --version 2>&1)（${SYSTEM_PY}）"

info "后端：创建虚拟环境"
if [ -d "$BACKEND/.venv" ] && resolve_venv_py; then
  ok "已存在，跳过"
else
  if [ -d "$BACKEND/.venv" ]; then
    # 从别的操作系统拷过来的 .venv 里是 Scripts\python.exe 或另一套路径，
    # 本机无法执行。虚拟环境可重建，直接删掉重来。
    warn "现有 .venv 无法在本机使用（可能来自其他操作系统），正在重建"
    rm -rf "$BACKEND/.venv"
  fi
  "$SYSTEM_PY" -m venv "$BACKEND/.venv"
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
if [ "$IS_WINDOWS" = 1 ]; then
  printf '    %s终端 1%s  scripts\\dev-backend.cmd\n' "$C_DIM" "$C_RESET"
  printf '    %s终端 2%s  scripts\\dev-frontend.cmd\n' "$C_DIM" "$C_RESET"
else
  printf '    %s终端 1%s  bash scripts/dev-backend.sh\n' "$C_DIM" "$C_RESET"
  printf '    %s终端 2%s  bash scripts/dev-frontend.sh\n' "$C_DIM" "$C_RESET"
fi
printf '\n'
printf '  前端    http://localhost:5173\n'
printf '  API 文档 http://127.0.0.1:8000/docs\n'
printf '  账号    admin / admin123456 %s（请登录后立即修改）%s\n' "$C_DIM" "$C_RESET"
