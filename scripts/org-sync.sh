#!/usr/bin/env bash
# 组织数据（用户 / 部门 / 角色）导出与导入 —— 在 Docker 环境之间搬运测试数据。
#
#   bash scripts/org-sync.sh export [输出文件]          # 默认 ./org-data.json
#   bash scripts/org-sync.sh import <文件> [选项]        # 选项透传给 python 脚本
#
# 常用流程：本机导出 → 把 JSON 拷到目标机器 → 目标机器导入。
#
#   bash scripts/org-sync.sh export
#   scp org-data.json user@target:/path/to/lowcode-platform/
#   # 目标机器（仓库根目录）：
#   bash scripts/org-sync.sh import org-data.json
#
# 导入默认只补缺失。想覆盖目标环境已有资料加 --update；连密码一起覆盖
# 再加 --update-passwords。先演练可加 --dry-run。
#
# 依赖：当前目录的 docker compose 已启动 backend 服务。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

cd "$ROOT"

# 容器内的临时中转文件；导入/导出都是「先落在容器里，再 cp 出来/拷进去」，
# 避免 docker compose exec 的 TTY 混进 JSON。
TMP=/tmp/flowform-org-sync.json

usage() {
  cat >&2 <<'EOF'
用法：
  bash scripts/org-sync.sh export [输出文件]
  bash scripts/org-sync.sh import <文件> [--dry-run] [--update] [--update-passwords] [--replace-roles]

示例：
  bash scripts/org-sync.sh export                 # 导出到 ./org-data.json
  bash scripts/org-sync.sh import org-data.json --dry-run
  bash scripts/org-sync.sh import org-data.json --update --update-passwords
EOF
}

ACTION="${1:-}"
case "$ACTION" in
  export)
    OUT="${2:-$ROOT/org-data.json}"
    info "从 backend 容器导出组织数据"
    docker compose exec -T backend python -m app.scripts.org_sync export -o "$TMP"
    docker compose cp "backend:$TMP" "$OUT"
    docker compose exec -T backend rm -f "$TMP"
    ok "已导出到 $OUT"
    ;;
  import)
    SRC="${2:-}"
    if [ -z "$SRC" ]; then
      usage
      exit 1
    fi
    shift 2
    if [ ! -f "$SRC" ]; then
      fail "文件不存在：$SRC"
      exit 1
    fi
    info "导入组织数据：$SRC${*:+（$*}）"
    docker compose cp "$SRC" "backend:$TMP"
    docker compose exec -T backend python -m app.scripts.org_sync import -i "$TMP" "$@" || {
      rc=$?
      docker compose exec -T backend rm -f "$TMP" || true
      exit "$rc"
    }
    docker compose exec -T backend rm -f "$TMP"
    ;;
  *)
    usage
    exit 1
    ;;
esac
