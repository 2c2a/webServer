"""
2c2a 应用配置

使用 pydantic-settings 管理配置，支持环境变量和 .env 文件
"""

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ========== 核心 ==========
    debug: bool = False
    secret_key: str = "change-me-in-production-32-chars-min!!"
    demo_mode: bool = False

    # ========== 数据库 ==========
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "2c2a"
    db_user: str = "postgres"
    db_password: str = ""
    db_pool_size: int = 20
    db_max_overflow: int = 10
    db_pool_recycle: int = 300

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """同步 URL，供 Alembic 迁移使用"""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    # ========== Redis ==========
    redis_url: str = "redis://localhost:6379/0"

    # ========== Huey ==========
    huey_redis_db: int = 1
    huey_immediate: bool = False  # True 时同步执行（调试用）

    @property
    def huey_redis_url(self) -> str:
        return self.redis_url.replace("/0", f"/{self.huey_redis_db}")

    # ========== JWT ==========
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 7

    # ========== 会话 ==========
    session_expire_seconds: int = 3600
    session_cookie_name: str = "2c2a_session"
    session_cookie_secure: bool = True
    session_cookie_httponly: bool = True
    session_cookie_samesite: str = "Lax"

    # ========== CORS ==========
    cors_allowed_origins: str = "http://localhost:8000,https://localhost"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    # ========== 安全 ==========
    allowed_hosts: str = "localhost,127.0.0.1"
    csrf_trusted_origins: str = "https://localhost"

    # ========== WinRM ==========
    winrm_timeout: int = 30
    winrm_max_retries: int = 3

    # ========== Gateway ==========
    gateway_enabled: bool = False
    gateway_control_socket: str = "/run/2c2a/control.sock"
    gateway_paa_token_signing_key: str = "change-me-32-chars-minimum!!"
    gateway_paa_token_expiry_seconds: int = 600
    gateway_address: str = "rdp.2c2a.com"
    gateway_port: int = 443

    # ========== RDP ==========
    rdp_domain: str = "2c2a.com"

    # ========== 限流 ==========
    login_rate_limit: int = 5
    api_rate_limit: int = 100

    # ========== 日志 ==========
    log_level: str = "INFO"
    log_file: str = ""

    # ========== SMTP ==========
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""

    # ========== Bootstrap ==========
    bootstrap_shared_salt: str = ""

    # ========== 隧道 ==========
    tunnel_releases_url: str = "https://api.github.com/repos/2c2a/tunnel/releases/latest"
    tunnel_gateway_url: str = "wss://gateway.2c2a.com:9000"

    # ========== 验证码 ==========
    captcha_provider: str = "none"

    # ========== 文件路径 ==========
    static_dir: str = str(BASE_DIR / "static")
    template_dir: str = str(BASE_DIR / "templates")
    media_dir: str = str(BASE_DIR / "media")

    # ========== 加密 ==========
    encryption_key: str = ""  # Fernet key，留空则自动生成

    @property
    def is_production(self) -> bool:
        return not self.debug


@lru_cache
def get_settings() -> Settings:
    return Settings()
