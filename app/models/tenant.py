"""租户与系统配置模型。

包含全局系统配置（单例）、站点组、站点组配置覆盖与站点组主机名绑定。
所有模型继承 Base，需要时间戳的混入 TimestampMixin。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SystemConfig(Base, TimestampMixin):
    """系统全局配置（单例，id 固定 = 1）。

    存储 SMTP、验证码、站点外观、注册策略等全局配置。
    敏感字段 smtp_password_cipher 使用字段级加密，不存明文。
    """

    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # ── SMTP 配置 ──
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_encryption: Mapped[str] = mapped_column(String(8), default="TLS")
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password_cipher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    smtp_from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── 验证码配置 ──
    captcha_provider: Mapped[str] = mapped_column(String(32), default="none")
    captcha_type: Mapped[str] = mapped_column(String(32), default="SLIDER")
    captcha_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    captcha_required_on_login: Mapped[bool] = mapped_column(Boolean, default=True)
    captcha_required_on_register: Mapped[bool] = mapped_column(Boolean, default=True)
    captcha_required_on_email: Mapped[bool] = mapped_column(Boolean, default=False)
    login_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    register_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── 站点外观 ──
    site_name: Mapped[str] = mapped_column(String(100), default="2c2a")
    site_icon: Mapped[str] = mapped_column(String(500), default="")

    # ── 注册策略 ──
    enable_registration: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 备案信息 ──
    icp_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    police_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── 邮箱后缀白/黑名单（每行一个后缀）──
    email_suffix_whitelist: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_suffix_blacklist: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 本地访问锁定 ──
    local_access_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 主机名品牌绑定 ──
    hostname_branding: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class SiteGroup(Base, TimestampMixin):
    """站点组：实现多租户数据隔离的顶层实体。

    一个站点组拥有独立的配置覆盖、主机名绑定、成员与管理员。
    """

    __tablename__ = "site_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_name: Mapped[str] = mapped_column(String(100), default="")
    site_icon: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── 关系 ──
    # 管理员（M2M → user_site_group_admins）
    admins: Mapped[list[User]] = relationship(  # noqa: F821
        secondary="user_site_group_admins",
        back_populates="admin_site_groups",
        lazy="selectin",
    )
    # 成员（M2M → user_site_groups）
    members: Mapped[list[User]] = relationship(  # noqa: F821
        secondary="user_site_groups",
        back_populates="site_groups",
        lazy="selectin",
    )
    # 配置覆盖（OneToOne）
    config: Mapped[SiteGroupConfig | None] = relationship(
        back_populates="site_group",
        uselist=False,
        cascade="all, delete-orphan",
    )
    # 主机名绑定（OneToMany）
    hostnames: Mapped[list[SiteGroupHostname]] = relationship(
        back_populates="site_group",
        cascade="all, delete-orphan",
    )


class SiteGroupConfig(Base, TimestampMixin):
    """站点组配置覆盖（OneToOne → SiteGroup）。

    字段留空（NULL）表示使用 SystemConfig 的全局默认值。
    """

    __tablename__ = "site_group_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    site_group_id: Mapped[int] = mapped_column(
        ForeignKey("site_group.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # ── SMTP 配置覆盖 ──
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_encryption: Mapped[str | None] = mapped_column(String(8), nullable=True)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password_cipher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    smtp_from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── 验证码配置覆盖 ──
    captcha_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    login_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    register_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ── 注册与邮箱配置覆盖 ──
    enable_registration: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    email_suffix_whitelist: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_suffix_blacklist: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 站点外观配置覆盖 ──
    site_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    site_icon: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icp_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    police_number: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # ── 关系 ──
    site_group: Mapped[SiteGroup] = relationship(back_populates="config")


class SiteGroupHostname(Base):
    """站点组主机名绑定：将 HTTP Host 头映射到站点组。"""

    __tablename__ = "site_group_hostname"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    site_group_id: Mapped[int] = mapped_column(
        ForeignKey("site_group.id", ondelete="CASCADE"), nullable=False
    )

    # ── 关系 ──
    site_group: Mapped[SiteGroup] = relationship(back_populates="hostnames")
