#!/usr/bin/env bash
# 兼容入口：真实实现在 testing/scripts/api.sh。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"
exec bash "$ROOT/testing/scripts/api.sh" "$@"
