"""全局配置（pydantic-settings）。

所有配置通过环境变量 / .env 文件注入，启动时一次性加载并校验。
密钥类配置（Ed25519、AES-GCM master key、BLAKE2b cache key）生产环境必须显式提供。
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # /workspace


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 运行环境 ──
    app_name: str = "2c2a"
    debug: bool = False
    env: str = "production"  # production / staging / development

    # ── Granian / FastAPI ──
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    secret_key: str = ""  # 兼容旧字段，仅用于派生非关键用途

    # ── 数据库 ──
    db_engine: str = "sqlite"  # sqlite / postgresql / mysql
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "2c2a"
    db_user: str = "2c2a"
    db_password: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ── Redis ──
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True

    # ── 安全密钥（生产必须显式配置）──
    # Ed25519 私钥（PEM），用于签发 Access Token JWT
    ed25519_private_key_pem: str = ""
    # Ed25519 公钥（PEM），用于验签
    ed25519_public_key_pem: str = ""
    # AES-GCM 主密钥（32 字节 base64），用于加密 Refresh Token 与字段级加密
    crypto_master_key_b64: str = ""
    # keyed-BLAKE2b 边缘缓存签名密钥（任意长度）
    cache_signing_key: str = ""

    # ── 认证 ──
    access_token_ttl_seconds: int = 300  # 5 分钟
    refresh_token_ttl_days: int = 7
    refresh_token_cookie_name: str = "2c2a_rt"
    # 前端 BLAKE2b 预哈希输出长度（字节），用于防 DoS 截断
    password_prehash_bytes: int = 64

    # ── Argon2id 参数 ──
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536  # 64 MiB
    argon2_parallelism: int = 2

    # ── 缓存 ──
    app_shell_cache_ttl: int = 300  # App Shell 边缘缓存 5 分钟
    tenant_cache_ttl: int = 300  # 租户配置缓存
    fragment_cache_ttl: int = 0  # HTMX 片段默认不缓存（动态）

    # ── WinRM ──
    winrm_timeout: int = 30
    winrm_max_retries: int = 3
    winrm_transport_max_conns: int = 100

    # ── 邮件 / SMTP ──
    # 全局开关：关闭后所有邮件发送直接跳过（仍走 dev fallback 行为）
    email_enabled: bool = True
    # SMTP 连接与单次操作超时（秒）
    smtp_timeout_seconds: int = 15
    # 瞬时故障重试次数（连接拒绝/超时等），0 表示不重试
    smtp_max_retries: int = 2
    # 重试退避基数（秒），实际退避 = base * 2^(attempt-1)
    smtp_retry_backoff_base_seconds: float = 0.5
    # 密码重置链接基址：留空时由请求 Host 头推导
    # 多租户/反代场景建议显式配置，例如 https://example.com
    password_reset_link_base_url: str = ""
    # 密码重置链接路径（前端路由）
    password_reset_link_path: str = "/reset-password"

    # ── 邮箱验证码（注册）──
    # 验证码有效期（秒），默认 10 分钟
    email_code_ttl_seconds: int = 600
    # 同一邮箱两次发送的最小间隔（秒），防止滥用
    email_code_resend_interval_seconds: int = 60
    # 验证码最大尝试次数（用尽后令牌失效，需重新获取）
    email_code_max_attempts: int = 5

    # ── 速率限制 ──
    login_rate_limit: int = 5
    api_rate_limit: int = 100

    # ── 行为验证码 ──
    captcha_enabled: bool = True  # 全局开关（关闭则登录/注册跳过校验）
    captcha_default_type: str = ""  # 默认类型，留空则随机
    captcha_ttl_seconds: int = 300  # 题目有效期
    captcha_max_attempts: int = 5  # 最大尝试次数
    captcha_required_on_login: bool = True
    captcha_required_on_register: bool = True

    # ── 可信代理（用于获取真实 IP）──
    trusted_proxy_ips: str = ""
    use_x_forwarded_for: bool = True

    # ── 开发模式自动生成密钥 ──
    @field_validator("secret_key")
    @classmethod
    def _ensure_secret(cls, v: str, info) -> str:
        if not v:
            if info.data.get("debug"):
                return secrets.token_urlsafe(48)
            raise ValueError("SECRET_KEY 必须在生产环境显式配置")
        return v

    @computed_field  # type: ignore[misc]
    @property
    def is_prod(self) -> bool:
        return self.env == "production" and not self.debug

    @property
    def database_url(self) -> str:
        """异步数据库 URL。"""
        e = self.db_engine
        if e == "sqlite":
            return f"sqlite+aiosqlite:///{BASE_DIR / (self.db_name + '.db')}"
        if e == "postgresql":
            return (
                f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        if e == "mysql":
            return (
                f"mysql+aiomysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        raise ValueError(f"不支持的数据库引擎: {e}")

    @property
    def sync_database_url(self) -> str:
        """同步数据库 URL（仅 Alembic 离线使用）。"""
        e = self.db_engine
        if e == "sqlite":
            return f"sqlite:///{BASE_DIR / (self.db_name + '.db')}"
        if e == "postgresql":
            return (
                f"postgresql+psycopg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        if e == "mysql":
            return (
                f"mysql+pymysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        raise ValueError(f"不支持的数据库引擎: {e}")

    @property
    def trusted_proxies(self) -> set[str]:
        return {ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
