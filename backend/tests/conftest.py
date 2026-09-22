"""测试夹具。

隔离策略：每个测试跑在一个**外层事务**里，结束后整体回滚。
SQLAlchemy 2.0 的 `join_transaction_mode="create_savepoint"` 让业务代码里的
`session.commit()` 只释放 savepoint，而不会提交外层事务 —— 这样既保留了
「service 层 commit」的真实行为，又保证测试之间互不污染。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import RoleCode, UserStatus
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app as fastapi_app
from app.models import Role, User, UserRole
from app.seeds.init_admin import run_seed

ADMIN_PASSWORD = "admin123456"
USER_PASSWORD = "user123456"


@pytest.fixture(scope="session")
def test_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """独立的测试库。刻意用文件而非 :memory:，让连接池行为更接近真实。"""
    db_path = tmp_path_factory.mktemp("flowform-test") / "test.db"
    return Settings(
        database_url=f"sqlite:///{db_path.as_posix()}",
        jwt_secret="test-only-secret",
        admin_username="admin",
        admin_password=ADMIN_PASSWORD,
        admin_email="admin@example.com",
        seed_demo_org=True,
    )


@pytest.fixture(scope="session")
def engine(test_settings: Settings):
    eng = create_engine(
        test_settings.database_url, connect_args={"check_same_thread": False}
    )

    @event.listens_for(eng, "connect")
    def _configure_sqlite(dbapi_connection, _record) -> None:
        # 关掉 pysqlite 自带的隐式事务管理，改由 SQLAlchemy 显式发 BEGIN ——
        # 否则 connection.begin() 只是名义上的事务，而 savepoint 在 SQLite 里
        # 一旦是最外层，RELEASE 就等于 COMMIT，测试数据会真的落盘、互相串。
        # 这是 SQLAlchemy 文档里 SQLite 事务测试的标准做法。
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        # 与生产引擎保持一致的行为（db/session.py 也开了这个）
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(eng, "begin")
    def _emit_begin(conn) -> None:
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine, test_settings: Settings) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        autoflush=False,
        expire_on_commit=False,
    )
    try:
        # 每个测试都从「已初始化好的系统」开始：内置角色 + 示例部门 + 管理员
        run_seed(session, test_settings)
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    fastapi_app.dependency_overrides[get_db] = lambda: db
    # 挡掉 lifespan 里的种子：它会用 app.db.session.SessionLocal 打真实数据库。
    # `_bootstrap` 在调用时按模块全局查找这个名字，所以替换有效。
    monkeypatch.setattr("app.main.run_seed", lambda *_, **__: None)
    yield TestClient(fastapi_app)
    fastapi_app.dependency_overrides.clear()


# --------------------------------------------------------------------------- 账号


def login_as(client: TestClient, username: str, password: str) -> dict[str, str]:
    """登录并返回可直接用于请求的 Authorization 头。测试里构造非常规账号时会用到。"""
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def admin_headers(client: TestClient) -> dict[str, str]:
    return login_as(client, "admin", ADMIN_PASSWORD)


@pytest.fixture
def normal_user(db: Session) -> User:
    """一个只有普通权限（无任何角色）的启用用户。"""
    user = User(
        username="zhangsan",
        real_name="张三",
        password_hash=hash_password(USER_PASSWORD),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def normal_headers(client: TestClient, normal_user: User) -> dict[str, str]:
    return login_as(client, normal_user.username, USER_PASSWORD)


@pytest.fixture
def designer_role(db: Session) -> Role:
    return db.scalar(select(Role).where(Role.code == RoleCode.DESIGNER))


@pytest.fixture
def platform_admin_role(db: Session) -> Role:
    return db.scalar(select(Role).where(Role.code == RoleCode.PLATFORM_ADMIN))


def make_user(
    db: Session,
    *,
    username: str,
    password: str = USER_PASSWORD,
    real_name: str | None = None,
    is_superuser: bool = False,
    role: Role | None = None,
) -> User:
    """直接建号（绕过 API），用于构造权限边界场景。"""
    user = User(
        username=username,
        real_name=real_name or username,
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE,
        is_superuser=is_superuser,
    )
    db.add(user)
    db.flush()
    if role is not None:
        db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user
