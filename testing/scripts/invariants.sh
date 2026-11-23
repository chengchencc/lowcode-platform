#!/usr/bin/env bash
# G3 引擎不变量：随机流程 + 随机动作序列。
#
#   bash scripts/invariants.sh                 # 默认 200 轮
#   INVARIANT_ROUNDS=1000 bash scripts/invariants.sh
#   bash scripts/invariants.sh -k something    # pytest 参数透传
#
# 不启动服务、不连开发库；使用后端测试的隔离 SQLite。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../scripts/_common.sh"

require_venv

cd "$ROOT"
PYTHONPATH="$BACKEND" "$VENV_PY" -m pytest testing/invariants -q -n0 "$@"
