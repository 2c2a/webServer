"""
仪表盘与系统配置模型

包含 DashboardWidget, SystemConfig, SiteGroup, SiteGroupHostname
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import site_group_admins, user_site_groups


class DashboardWidget(Base):
    """仪表盘组件模型"""
    __tablename__ = "dashboard_widget"
    __table_args__ = (
        Index("ix_widget_widget_type", "widget_type"),
        Index("ix_widget_is_enabled", "is_enabled"),
        Index("ix_widget_display_order", "display_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    widget_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    widget_config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<DashboardWidget {self.title}>"


class SystemConfig(Base):
    """系统配置模型（单例，id 始终为 1）"""
    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # SMTP 配置
    smtp_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    smtp_use_tls: Mapped[bool] = mapped_column(Boolean, default=True)
    smtp_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    smtp_from_email: Mapped[str | None] = mapped_column(String(254), nullable=True)

    # 验证码配置
    captcha_provider: Mapped[str] = mapped_column(String(32), default="none")
    captcha_type: Mapped[str] = mapped_column(String(32), default="SLIDER")
    login_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    register_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email_captcha_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # 站点配置
    site_name: Mapped[str] = mapped_column(String(100), default="2c2a")
    enable_registration: Mapped[bool] = mapped_column(Boolean, default=False)
    icp_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    police_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email_suffix_whitelist: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_suffix_blacklist: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_access_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    hostname_branding: Mapped[dict] = mapped_column(JSON, default=dict)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<SystemConfig {self.site_name}>"


class SiteGroup(Base):
    """站点组模型"""
    __tablename__ = "sitegroup"
    __table_args__ = (
        Index("ix_sitegroup_slug", "slug"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    site_name: Mapped[str] = mapped_column(String(100), default="")
    site_icon: Mapped[str] = mapped_column(String(500), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    members: Mapped[list["User"]] = relationship(
        "User", secondary=user_site_groups, back_populates="site_groups"
    )
    admins: Mapped[list["User"]] = relationship(
        "User", secondary=site_group_admins, back_populates="admin_site_groups"
    )
    hosts: Mapped[list["Host"]] = relationship("Host", back_populates="site_group")
    host_groups: Mapped[list["HostGroup"]] = relationship("HostGroup", back_populates="site_group")
    hostnames: Mapped[list["SiteGroupHostname"]] = relationship("SiteGroupHostname", back_populates="site_group")

    def __repr__(self) -> str:
        return f"<SiteGroup {self.name}>"


class SiteGroupHostname(Base):
    """站点组主机名映射"""
    __tablename__ = "sitegroup_hostname"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    site_group_id: Mapped[str] = mapped_column(String(36), ForeignKey("sitegroup.id"), nullable=False)

    # relationships
    site_group: Mapped["SiteGroup"] = relationship("SiteGroup", back_populates="hostnames")

    def __repr__(self) -> str:
        return f"<SiteGroupHostname {self.hostname}>"
