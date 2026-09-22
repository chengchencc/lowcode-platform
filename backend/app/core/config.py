"""应用配置。所有可变项集中在此，通过环境变量或 backend/.env 覆盖。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录，用于把相对路径（SQLite 文件、.env）解析成绝对路径，
# 避免「从不同目录启动 uvicorn 时数据库文件位置不一致」。
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 应用 ----
    app_name: str = "FlowForm"
    debug: bool = True
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- 数据库 ----
    # SQLite 与 MySQL 的连接串都走这里，代码中不得出现方言判断（决策 D1）。
    database_url: str = f"sqlite:///{BACKEND_DIR / 'flowform.db'}"
    sql_echo: bool = False

    # ---- 认证 ----
    jwt_secret: str = "dev-only-secret-please-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    refresh_token_expire_minutes: int = 10080

    # ---- 初始化种子（F6.5）----
    admin_username: str = "admin"
    admin_password: str = "admin123456"
    admin_real_name: str = "平台管理员"
    admin_email: str | None = "admin@example.com"
    seed_demo_org: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def resolve_database_url(self) -> str:
        """把 SQLite 的相对路径锚定到 backend/，让启动目录不再影响结果。"""
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix) and not self.database_url.startswith("sqlite:////"):
            rel = self.database_url[len(prefix) :]
            if rel and rel != ":memory:":
                # 统一成正斜杠：Windows 反斜杠路径在 URL 里会被 alembic.ini 的
                # 插值语法和 SQLAlchemy 的 URL 解析两头夹击
                return f"{prefix}{(BACKEND_DIR / rel).resolve().as_posix()}"
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
