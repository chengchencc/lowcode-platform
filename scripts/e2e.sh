#!/usr/bin/env bash
# 兼容入口：真实实现已迁到 testing/scripts/e2e.sh。
# 保留这个文件名，README 与既有命令（bash scripts/e2e.sh ...）不用改。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
exec bash "$ROOT/testing/scripts/e2e.sh" "$@"
