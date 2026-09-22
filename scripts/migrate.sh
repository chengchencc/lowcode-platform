#!/usr/bin/env bash
# Alembic 迁移助手。不传参数时等价于 `alembic upgrade head`。
#
#   bash scripts/migrate.sh                                   # 升到最新
#   bash scripts/migrate.sh current                            # 当前版本
#   bash scripts/migrate.sh history                            # 迁移历史
#   bash scripts/migrate.sh downgrade -1                       # 回退一步
#   bash scripts/migrate.sh revision --autogenerate -m "描述"   # 依模型生成迁移
#
# 生成迁移后记得打开 alembic/versions/ 下的新文件核对一遍 ——
# autogenerate 不会识别重命名，会误判成「删旧列 + 加新列」。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_venv
ensure_env_file

CMD="${1:-upgrade}"
if [ "$#" -gt 0 ]; then shift; fi
if [ "$CMD" = "upgrade" ] && [ "$#" -eq 0 ]; then
  set -- head
fi

info "alembic $CMD $*  （数据库类型：$(database_kind)）"
cd "$BACKEND"
exec "$VENV_PY" -m alembic "$CMD" "$@"
