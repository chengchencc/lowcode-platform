#!/usr/bin/env bash
# E2E 专用环境变量。由 e2e.sh / e2e-reset.sh 在 source _common.sh 之后 source。
#
# 关键点：数据库与附件目录都指向 testing/.runtime/e2e/，绝不碰 backend/flowform.db。
# 相对路径由 app.core.config.resolve_database_url() 锚定到 backend/，跨平台一致。

export E2E_DIR="$ROOT/testing/.runtime/e2e"
export E2E_BACKEND_PORT="${E2E_BACKEND_PORT:-8000}"
export E2E_FRONTEND_PORT="${E2E_FRONTEND_PORT:-5173}"
export E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:$E2E_FRONTEND_PORT}"
export E2E_API_URL="${E2E_API_URL:-http://127.0.0.1:$E2E_BACKEND_PORT/api/v1}"

export DEBUG=false
export SQL_ECHO=false
# 默认 SQLite；CI/nightly 可通过 E2E_DATABASE_URL 覆盖为 MySQL/PG。
export DATABASE_URL="${E2E_DATABASE_URL:-sqlite:///../testing/.runtime/e2e/e2e.db}"
export STORAGE_ROOT="../testing/.runtime/e2e/storage"
export APP_TIMEZONE="Asia/Shanghai"

# 测试专用密钥；不是生产配置
export JWT_SECRET="e2e-only-secret-do-not-use-anywhere-else"

export SEED_DEMO_ORG=true
export SEED_DEMO_ACCOUNTS=true
export SEED_SAMPLE_FLOWS=true
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=admin123456
export ADMIN_REAL_NAME=平台管理员
export ADMIN_EMAIL=admin@example.com

export AI_ENABLED=false
export CORS_ORIGINS="http://localhost:$E2E_FRONTEND_PORT,http://127.0.0.1:$E2E_FRONTEND_PORT"
