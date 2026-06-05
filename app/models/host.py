"""
主机管理模型

包含 Host, HostGroup
TunnelConnectionAdapter 逻辑已移至 services 层
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Many-to-many 关联表：主机管理员
host_administrators = Table(
    "host_administrators",
    Base.metadata,
    Column("host_id", String(36), ForeignKey("host.id"), primary_key=True),
    Column("user_id", String(36), ForeignKey("user.id"), primary_key=True),
)

# Many-to-many 关联表：主机提供商
host_providers = Table(
    "host_providers",
    Base.metadata,
    Column("host_id", String(36), ForeignKey("host.id"), primary_key=True),
    Column("user_id", String(36), ForeignKey("user.id"), primary_key=True),
)

# Many-to-many 关联表：主机组 <-> 主机
hostgroup_hosts = Table(
    "hostgroup_hosts",
    Base.metadata,
    Column("hostgroup_id", String(36), ForeignKey("hostgroup.id"), primary_key=True),
    Column("host_id", String(36), ForeignKey("host.id"), primary_key=True),
)

# Many-to-many 关联表：主机组提供商
hostgroup_providers = Table(
    "hostgroup_providers",
    Base.metadata,
    Column("hostgroup_id", String(36), ForeignKey("hostgroup.id"), primary_key=True),
    Column("user_id", String(36), ForeignKey("user.id"), primary_key=True),
)


class Host(Base):
    """主机模型"""
    __tablename__ = "host"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    os_type: Mapped[str] = mapped_column(String(20), default="windows")
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    connection_type: Mapped[str] = mapped_column(String(20), default="winrm")
    auth_method: Mapped[str] = mapped_column(String(20), default="ntlm")
    port: Mapped[int] = mapped_column(Integer, default=5985)
    rdp_port: Mapped[int] = mapped_column(Integer, default=3389)
    use_ssl: Mapped[bool] = mapped_column(Boolean, default=False)
    username: Mapped[str] = mapped_column(String(100), default="")
    _password: Mapped[str] = mapped_column("password", String(255), default="")  # 加密存储
    cert_pem_path: Mapped[str] = mapped_column(String(512), default="")
    cert_key_path: Mapped[str] = mapped_column(String(512), default="")
    os_version: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default="offline")
    description: Mapped[str] = mapped_column(Text, default="")

    # 隧道相关字段
    tunnel_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    tunnel_status: Mapped[str] = mapped_column(String(20), default="no_tunnel")
    tunnel_connected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tunnel_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tunnel_client_version: Mapped[str] = mapped_column(String(50), default="")
    tunnel_client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    tunnel_public_key: Mapped[str] = mapped_column(Text, default="")

    # 证书相关字段
    cert_root: Mapped[str] = mapped_column(String(2), default="")
    cert_sub: Mapped[str] = mapped_column(String(2), default="")
    _pfx_password: Mapped[str] = mapped_column("pfx_password", String(255), default="")  # 加密存储
    ntlm_fallback_user: Mapped[str] = mapped_column(String(100), default="")
    _ntlm_fallback_password: Mapped[str] = mapped_column(
        "ntlm_fallback_password", String(255), default=""
    )  # 加密存储
    cert_activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cert_provision_status: Mapped[str] = mapped_column(String(20), default="not_started")

    # 外键
    site_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sitegroup.id"), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    administrators: Mapped[list["User"]] = relationship(
        "User", secondary=host_administrators, back_populates="managed_hosts"
    )
    providers: Mapped[list["User"]] = relationship(
        "User", secondary=host_providers, back_populates="provider_hosts"
    )
    site_group: Mapped["SiteGroup | None"] = relationship("SiteGroup", back_populates="hosts")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    host_groups: Mapped[list["HostGroup"]] = relationship("HostGroup", secondary=hostgroup_hosts, back_populates="hosts")

    def __repr__(self) -> str:
        return f"<Host {self.name}>"


class HostGroup(Base):
    """主机组模型"""
    __tablename__ = "hostgroup"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # 外键
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    site_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sitegroup.id"), nullable=True)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    hosts: Mapped[list["Host"]] = relationship("Host", secondary=hostgroup_hosts, back_populates="host_groups")
    providers: Mapped[list["User"]] = relationship(
        "User", secondary=hostgroup_providers, back_populates="provider_hostgroups"
    )
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    site_group: Mapped["SiteGroup | None"] = relationship("SiteGroup", back_populates="host_groups")

    def __repr__(self) -> str:
        return f"<HostGroup {self.name}>"
