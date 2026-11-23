#!/usr/bin/env bash
# 重置 E2E 独立环境：删除 testing/.runtime/e2e → 迁移 → 种子 → 输出账号表。
#
#   bash testing/scripts/e2e-reset.sh
#
# 绝不触碰开发库 backend/flowform.db。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../scripts/_common.sh"
source "$SCRIPT_DIR/e2e-env.sh"

require_venv

info "重置 E2E 环境：$E2E_DIR"
if ! rm -rf "$E2E_DIR" 2>/dev/null; then
  fail "无法清空 $E2E_DIR：可能有 E2E 服务仍在运行并占用数据库"
  for port in "$E2E_BACKEND_PORT" "$E2E_FRONTEND_PORT"; do
    pid="$(port_holder "$port")"
    [ -n "$pid" ] && printf '    端口 %s 被 PID %s 占用\n' "$port" "$pid" >&2
  done
  printf '    先结束占用进程，或执行：bash scripts/e2e.sh --no-reset（复用现有数据）\n' >&2
  exit 1
fi
mkdir -p "$E2E_DIR/storage"
ok "已清空旧库与附件目录"

info "执行数据库迁移"
MIGRATE_LOG="$E2E_DIR/migrate.log"
if ! (cd "$BACKEND" && "$VENV_PY" -m alembic upgrade head) > "$MIGRATE_LOG" 2>&1; then
  fail "迁移失败，日志：$MIGRATE_LOG"
  tail -n 40 "$MIGRATE_LOG" >&2 || true
  exit 1
fi
ok "迁移完成：$DATABASE_URL"

info "写入种子数据（管理员 / 示例部门 / 示例账号 / 示例流程）"
SEED_LOG="$E2E_DIR/seed.log"
if ! (
  cd "$BACKEND"
  "$VENV_PY" - <<'PY'
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.seeds.init_admin import run_seed

settings = get_settings()
with SessionLocal() as db:
    run_seed(db, settings)
    db.commit()
print("seed ok")
PY
) > "$SEED_LOG" 2>&1; then
  fail "种子写入失败，日志：$SEED_LOG"
  tail -n 40 "$SEED_LOG" >&2 || true
  exit 1
fi
ok "种子写入完成"

cat > "$E2E_DIR/accounts.md" <<'EOF'
# E2E 测试账号（仅隔离环境）

| 用户名 | 密码 | 姓名 | 部门 | 角色 |
|---|---|---|---|---|
| admin | admin123456 | 平台管理员 | 总公司 | 平台管理员（superuser） |
| zhangsan | demo123456 | 张三 | 技术部 | 无（普通发起人） |
| lisi | demo123456 | 李四 | 技术部 | 部门主管 |
| wangwu | demo123456 | 王五 | 财务部 | 财务 / 财务部主管 |
| zhaoliu | demo123456 | 赵六 | 总公司 | 设计者 / 总公司主管 |

- 数据库：`testing/.runtime/e2e/e2e.db`
- 附件：`testing/.runtime/e2e/storage/`
- 这些密码是公开测试密码，禁止用于任何可被外部访问的环境。
EOF

printf '\n'
ok "E2E 环境就绪"
printf '    数据库   %s\n' "$E2E_DIR/e2e.db"
printf '    账号表   %s\n' "$E2E_DIR/accounts.md"
printf '    下一步   bash scripts/e2e.sh\n'
