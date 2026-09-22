#!/usr/bin/env bash
# 跑全套校验：后端测试 + lint + 前端类型检查 + 构建。
#
#   bash scripts/check.sh
#
# 四项全部执行完再汇总（不提前退出），一次就能看到所有问题。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

require_venv
require_node

declare -a NAMES=()
declare -a STATUSES=()

run_step() {
  local name="$1"; shift
  printf '\n'
  info "$name"
  if "$@"; then
    NAMES+=("$name"); STATUSES+=("pass")
  else
    NAMES+=("$name"); STATUSES+=("FAIL")
  fi
}

run_backend_tests() { (cd "$BACKEND" && "$VENV_PY" -m pytest -q); }
run_backend_lint()  { (cd "$BACKEND" && "$VENV_PY" -m ruff check app tests); }
run_frontend_types() { (cd "$FRONTEND" && npm run --silent typecheck); }
# 渲染冒烟：真正挂载每个页面，抓「组件没注册」这类 typecheck/build 都放行的问题
run_frontend_render() { (cd "$FRONTEND" && npm run --silent test); }
run_frontend_build() { (cd "$FRONTEND" && npx --no-install vite build >/dev/null && echo "构建成功"); }

run_step "后端测试 (pytest)"        run_backend_tests
run_step "后端静态检查 (ruff)"      run_backend_lint
run_step "前端类型检查 (vue-tsc)"   run_frontend_types
run_step "前端渲染测试 (vitest)"    run_frontend_render
run_step "前端构建 (vite build)"    run_frontend_build

printf '\n%s──────── 汇总 ────────%s\n' "$C_DIM" "$C_RESET"
failed=0
for i in "${!NAMES[@]}"; do
  if [ "${STATUSES[$i]}" = "pass" ]; then
    ok "${NAMES[$i]}"
  else
    fail "${NAMES[$i]}"
    failed=1
  fi
done

printf '\n'
if [ "$failed" -eq 0 ]; then
  ok "全部通过"
else
  fail "存在未通过的检查项"
fi
exit "$failed"
