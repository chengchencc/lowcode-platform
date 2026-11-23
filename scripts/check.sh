#!/usr/bin/env bash
# 校验。**默认全量**，也可以只跑受影响的一部分。
#
#   bash scripts/check.sh                 # 全量五项（提交前 / 里程碑收尾）
#   bash scripts/check.sh quick           # ruff + vue-tsc + vitest，约 1 分钟
#   bash scripts/check.sh backend         # pytest + ruff
#   bash scripts/check.sh backend tests/test_engine_service.py   # 只跑指定文件
#   bash scripts/check.sh frontend        # vue-tsc + vitest + build
#
# 迭代时用 quick 或指定文件；改动跨前后端、或准备提交时再跑全量。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

SCOPE="${1:-all}"
shift 2>/dev/null || true

# 只要求当前 scope 真正需要的运行时：
# backend 不需要前端 node_modules，frontend 也不需要 Python venv。
case "$SCOPE" in
  all|quick) require_venv; require_node ;;
  backend)   require_venv ;;
  frontend)  require_node ;;
esac

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

# 后端：可选地只跑指定测试文件（省下全量里的大头）
run_backend_tests() {
  if [ "$#" -gt 0 ]; then
    # 指定文件时**关掉并行**：pyproject 里的 `--dist loadfile` 会把同一个文件的
    # 测试压到一个 worker，单文件跑不但没并行收益，还白付 worker 启动开销。
    (cd "$BACKEND" && "$VENV_PY" -m pytest -q -n0 "$@")
  else
    (cd "$BACKEND" && "$VENV_PY" -m pytest -q)
  fi
}
run_backend_lint()  { (cd "$BACKEND" && "$VENV_PY" -m ruff check app tests); }
run_frontend_types() { (cd "$FRONTEND" && npm run --silent typecheck); }
run_frontend_render() { (cd "$FRONTEND" && npm run --silent test); }
run_frontend_build() { (cd "$FRONTEND" && npx --no-install vite build >/dev/null && echo "构建成功"); }

case "$SCOPE" in
  all)
    run_step "后端测试 (pytest)"        run_backend_tests
    run_step "后端静态检查 (ruff)"      run_backend_lint
    run_step "前端类型检查 (vue-tsc)"   run_frontend_types
    run_step "前端渲染测试 (vitest)"    run_frontend_render
    run_step "前端构建 (vite build)"    run_frontend_build
    ;;
  quick)
    # 迭代中最常用：三道快关卡，约 1 分钟
    run_step "后端静态检查 (ruff)"      run_backend_lint
    run_step "前端类型检查 (vue-tsc)"   run_frontend_types
    run_step "前端渲染测试 (vitest)"    run_frontend_render
    ;;
  backend)
    if [ "$#" -gt 0 ]; then
      run_step "后端测试 (pytest $*)"   run_backend_tests "$@"
    else
      run_step "后端测试 (pytest)"      run_backend_tests
    fi
    run_step "后端静态检查 (ruff)"      run_backend_lint
    ;;
  frontend)
    run_step "前端类型检查 (vue-tsc)"   run_frontend_types
    run_step "前端渲染测试 (vitest)"    run_frontend_render
    run_step "前端构建 (vite build)"    run_frontend_build
    ;;
  *)
    fail "未知范围：$SCOPE"
    printf '    可用：all（默认）| quick | backend [测试文件...] | frontend\n' >&2
    exit 2
    ;;
esac

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
