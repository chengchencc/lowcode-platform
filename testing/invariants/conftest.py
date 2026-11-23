"""G3 引擎不变量测试夹具。

复用后端测试的隔离数据库与「每例回滚」策略；本目录不在默认
`pytest` 路径里，由 `testing/scripts/invariants.sh` 单独运行。
"""

from tests.conftest import (  # noqa: F401
    _isolated_storage,
    db,
    engine,
    test_settings,
)
