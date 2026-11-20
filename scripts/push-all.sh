#!/usr/bin/env bash
# 双远端推送：origin（Gitee）与 github。
#
#   bash scripts/push-all.sh            # 当前分支
#   bash scripts/push-all.sh master     # 指定分支
#
# 两个远端分开推：GitHub 不通时不会阻塞 Gitee 已经成功的推送。

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_common.sh"

branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
if [ "$branch" = "HEAD" ]; then
  fail "当前是 detached HEAD，请指定分支名"
  exit 2
fi

if ! git remote get-url github >/dev/null 2>&1; then
  fail "未配置 github remote；先按 docs/GITHUB-MIGRATION.md 添加"
  exit 2
fi

info "推送到 Gitee（origin）：$branch"
git push origin "$branch"
ok "Gitee 完成"

info "推送到 GitHub（github）：$branch"
git push github "$branch"
ok "GitHub 完成"
