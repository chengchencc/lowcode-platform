#!/bin/sh
# 容器启动：等数据库 → 跑迁移 → 交给 CMD。
#
# 迁移放在**启动时**而不是构建时：构建镜像时数据库还不存在（也不该存在）。
# 首次启动会建全部表，之后每次启动都是幂等的 upgrade head。
# 种子数据不在这里：应用启动时自己幂等地补（见 app/seeds/），
# 这样本地直跑和容器跑的行为完全一致。
set -e

attempt=0
until alembic upgrade head; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "[entrypoint] 数据库 30 次重试后仍不可用，放弃启动" >&2
        exit 1
    fi
    echo "[entrypoint] 数据库尚未就绪，2 秒后重试（第 ${attempt} 次）"
    sleep 2
done

echo "[entrypoint] 迁移完成，启动服务：$*"
exec "$@"
