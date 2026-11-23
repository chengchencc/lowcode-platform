#!/usr/bin/env bash
# 构建独立验收设计用的 Spec Pack（生成物，不提交）。
#
#   bash scripts/build-spec-pack.sh
#
# 输出 testing/.runtime/spec-pack/：需求/设计/业务文档 + OpenAPI 契约，**不含任何实现源码**。
# 用途见 testing/acceptance/SPEC-PACK.md：让不知道实现的上下文独立设计用例。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../scripts/_common.sh"

require_venv

OUT="$ROOT/testing/.runtime/spec-pack"
BUSINESS_DOC="$ROOT/docs/需要支撑的真实业务流程/国家融资担保基金数字化平台运维服务项目-项目章程（合稿v2.0）.docx"

info "构建 Spec Pack：$OUT"
rm -rf "$OUT"
mkdir -p "$OUT/docs" "$OUT/api"

copy_doc() {
  local src="$ROOT/docs/$1"
  if [ ! -f "$src" ]; then
    fail "缺少文档：docs/$1"
    exit 1
  fi
  cp "$src" "$OUT/docs/$1"
}

for doc in \
  PRD-lowcode-form-approval.md \
  TECH-DESIGN.md \
  PHASE2-DESIGN.md \
  PHASE3-DESIGN.md \
  DEMO.md \
  REQ-OPT-FLOW-CONFIG.md \
  SEARCH-FILTER-PLAN.md
do
  copy_doc "$doc"
done

cp "$ROOT/testing/plan/TEST-PLAN.md" "$OUT/docs/TEST-PLAN.md"
cp "$ROOT/testing/acceptance/TEMPLATE.md" "$OUT/docs/TEMPLATE.md"
cp "$ROOT/testing/acceptance/TEST-DATA.md" "$OUT/docs/TEST-DATA.md"

if [ -f "$BUSINESS_DOC" ]; then
  "$VENV_PY" "$ROOT/testing/scripts/extract_docx_text.py" "$BUSINESS_DOC" "$OUT/docs/business-charter.md"
  ok "业务章程已抽取：docs/business-charter.md"
else
  warn "未找到业务章程 docx，Spec Pack 将不包含业务语义文档"
fi

info "导出 OpenAPI 契约"
(
  cd "$BACKEND"
  PYTHONPATH=. "$VENV_PY" - "$OUT/api/openapi.json" <<'PY'
import json
import sys

from app.main import app

with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as output:
    json.dump(app.openapi(), output, ensure_ascii=False, indent=2)
PY
)
ok "OpenAPI：api/openapi.json"

cat > "$OUT/README.md" <<'EOF'
# FlowForm Spec Pack（生成物）

本目录只包含**需求、设计、业务文档与接口契约**，不包含实现源码。

## 允许阅读

- `docs/` 下的全部 Markdown
- `api/openapi.json`（仅用于确认接口路径、字段、状态码）

## 禁止阅读

- 仓库中的 `backend/`、`frontend/`、`testing/e2e/`、`scripts/` 或任何源码/测试代码
- 不要根据字段名、表名、函数名反推业务规则
- 不要把"现有系统通常怎么做"当成需求

## 设计任务

按 `docs/TEMPLATE.md` 输出 P0 验收用例，覆盖 `docs/TEST-PLAN.md` §6 的场景 ID。
文档没有定义清楚的，列入"需求待确认项"，不要自行补规则。
EOF

printf '\n'
ok "Spec Pack 就绪：$OUT"
printf '    资料：%s\n' "$(find "$OUT" -type f | wc -l) 个文件"
printf '    下一步：把 %s 作为唯一资料，按 testing/acceptance/SPEC-PACK.md 的 Prompt 做独立设计\n' "$OUT"
