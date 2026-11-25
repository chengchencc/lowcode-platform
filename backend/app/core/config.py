"""应用配置。所有可变项集中在此，通过环境变量或 backend/.env 覆盖。"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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

    # ---- 展示时区 ----
    #: 数据统一存 naive UTC；首页「今日/本周/本月」按该时区计算边界
    app_timezone: str = "Asia/Shanghai"

    # ---- AI 辅助配置（M15）----
    #: 默认关闭；开启前需完成网络例外与模型供应商配置
    ai_enabled: bool = False
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"
    ai_timeout_seconds: int = 60
    ai_max_tokens: int = 4000
    #: 每用户每小时最多生成次数
    ai_rate_limit_per_hour: int = 20

    # ---- 认证 ----
    jwt_secret: str = "dev-only-secret-please-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    refresh_token_expire_minutes: int = 10080

    # ---- 附件存储（PRD §10 #4：V1 落本地磁盘 + DB 记元数据）----
    #: 相对路径会锚定到 backend/，和 SQLite 文件同样的处理
    storage_root: str = "storage"
    max_upload_mb: int = 20
    #: 扩展名白名单，逗号分隔
    allowed_extensions: str = (
        "jpg,jpeg,png,gif,bmp,webp,svg,"
        "pdf,doc,docx,xls,xlsx,ppt,pptx,"
        "txt,csv,md,json,xml,zip,rar,7z"
    )

    # ---- 初始化种子（F6.5 / M6）----
    admin_username: str = "admin"
    admin_password: str = "admin123456"
    admin_real_name: str = "平台管理员"
    admin_email: str | None = "admin@example.com"
    #: 示例部门树 + 初始管理员
    seed_demo_org: bool = True
    #: 示例账号（张三/李四/王五/赵六）。**密码是公开的**，
    #: 只在试用环境打开；上线前务必设为 false（容器形态见 .env.example）
    seed_demo_accounts: bool = False
    #: 示例流程库（请假 / 报销）。预置数据本身也要发布得出来，走的是同一套校验
    seed_sample_flows: bool = True

    @field_validator("app_name")
    @classmethod
    def _normalize_app_name(cls, value: str) -> str:
        """系统名称会显示在登录页、侧边栏和浏览器标题上，空值退回默认名。"""
        return value.strip() or "FlowForm"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def storage_path(self) -> Path:
        """附件存储根目录（绝对路径）。"""
        root = Path(self.storage_root)
        return root if root.is_absolute() else (BACKEND_DIR / root)

    @property
    def allowed_extension_set(self) -> set[str]:
        return {e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()}

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
