"""主机与主机组模型。

Host 表示一台可远程管理的 Windows/Linux 主机，支持 WinRM / 本地 WinServer / SSH 连接，
以及 NTLM 密码或证书认证。所有敏感密码字段使用 _cipher 后缀加密存储。
本模型已移除全部 tunnel_* 字段（隧道功能已废弃）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# ──────────────────────────────────────────────
# 多对多关联表
# ──────────────────────────────────────────────

# 主机 ↔ 授权管理员
host_administrators = Table(
    "host_administrators",
    Base.metadata,
    Column("host_id", Integer, ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

# 主机 ↔ 管理提供商
host_providers = Table(
    "host_providers",
    Base.metadata,
    Column("host_id", Integer, ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)

# 主机组 ↔ 主机
hostgroup_hosts = Table(
    "hostgroup_hosts",
    Base.metadata,
    Column("hostgroup_id", Integer, ForeignKey("host_group.id", ondelete="CASCADE"), primary_key=True),
    Column("host_id", Integer, ForeignKey("hosts.id", ondelete="CASCADE"), primary_key=True),
)

# 主机组 ↔ 管理提供商
hostgroup_providers = Table(
    "hostgroup_providers",
    Base.metadata,
    Column("hostgroup_id", Integer, ForeignKey("host_group.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Host(Base, TimestampMixin):
    """主机模型。

    连接类型: winrm / localwinserver / ssh（隧道模式已移除）。
    认证方式: ntlm（管理员账户密码）/ certificate（证书）。
    """

    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    os_type: Mapped[str] = mapped_column(String(20), default="windows")
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── 连接配置 ──
    connection_type: Mapped[str] = mapped_column(String(20), default="winrm")
    auth_method: Mapped[str] = mapped_column(String(20), default="ntlm")
    port: Mapped[int] = mapped_column(Integer, default=5985)
    rdp_port: Mapped[int] = mapped_column(Integer, default=3389)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 认证凭据（加密存储）──
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_cipher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cert_pem_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cert_key_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── 主机信息 ──
    os_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 关联 ──
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True
    )

    # ── 证书存储路径 ──
    cert_root: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cert_sub: Mapped[str | None] = mapped_column(String(2), nullable=True)
    pfx_password_cipher: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── NTLM 回退凭据（加密存储）──
    ntlm_fallback_user: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ntlm_fallback_password_cipher: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── 证书配置状态 ──
    cert_activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cert_provision_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # ── 关系 ──
    administrators: Mapped[list["User"]] = relationship(  # noqa: F821
        secondary=host_administrators,
        back_populates="managed_hosts",
        lazy="selectin",
    )
    providers: Mapped[list["User"]] = relationship(  # noqa: F821
        secondary=host_providers,
        back_populates="provider_hosts",
        lazy="selectin",
    )
    groups: Mapped[list["HostGroup"]] = relationship(  # noqa: F821
        secondary=hostgroup_hosts,
        back_populates="hosts",
        lazy="selectin",
    )
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )


class HostGroup(Base, TimestampMixin):
    """主机组：将多台主机分组管理。"""

    __tablename__ = "host_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True
    )

    # ── 关系 ──
    hosts: Mapped[list[Host]] = relationship(
        secondary=hostgroup_hosts,
        back_populates="groups",
        lazy="selectin",
    )
    providers: Mapped[list["User"]] = relationship(  # noqa: F821
        secondary=hostgroup_providers,
        back_populates="provider_hostgroups",
        lazy="selectin",
    )
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )
