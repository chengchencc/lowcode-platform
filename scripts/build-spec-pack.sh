#!/usr/bin/env bash
# 兼容入口：真实实现已迁到 testing/scripts/build-spec-pack.sh。
# 保留这个文件名，文档中的命令不用改。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
exec bash "$ROOT/testing/scripts/build-spec-pack.sh" "$@"
