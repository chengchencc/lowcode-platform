"""数据库引擎与会话。"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_URL = settings.resolve_database_url()


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # FastAPI 的同步路由跑在线程池里，连接可能跨线程复用
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True, "pool_recycle": 3600}


engine: Engine = create_engine(
    _URL,
    echo=settings.sql_echo,
    future=True,
    **_engine_kwargs(_URL),
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite 默认不校验外键，显式打开以免开发期漏掉约束错误，到 MySQL 才炸。"""
    if not _URL.startswith("sqlite"):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,  # 提交后仍可读对象属性，便于直接序列化返回值
)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每请求一个会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
