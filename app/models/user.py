"""
用户管理模型

包含 User, UserProfile, LoginLog, Group, GroupProfile, RegistrationLink
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Many-to-many 关联表：用户 <-> 用户组
user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("user.id"), primary_key=True),
    Column("group_id", String(36), ForeignKey("group.id"), primary_key=True),
)

# Many-to-many 关联表：用户 <-> 站点组（User.site_groups）
user_site_groups = Table(
    "user_site_groups",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("user.id"), primary_key=True),
    Column("sitegroup_id", String(36), ForeignKey("sitegroup.id"), primary_key=True),
)

# Many-to-many 关联表：站点组管理员（SiteGroup.admins）
site_group_admins = Table(
    "site_group_admins",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("user.id"), primary_key=True),
    Column("sitegroup_id", String(36), ForeignKey("sitegroup.id"), primary_key=True),
)


class Group(Base):
    """用户组模型（替代 Django auth.Group）"""
    __tablename__ = "group"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)

    # relationships
    users: Mapped[list["User"]] = relationship("User", secondary=user_groups, back_populates="groups")
    profile: Mapped["GroupProfile | None"] = relationship("GroupProfile", back_populates="group", uselist=False)
    registration_links: Mapped[list["RegistrationLink"]] = relationship("RegistrationLink", back_populates="group")

    def __repr__(self) -> str:
        return f"<Group {self.name}>"


class User(Base):
    """用户模型"""
    __tablename__ = "user"
    __table_args__ = (
        Index("ix_user_email", "email"),
        Index("ix_user_phone", "phone"),
        Index("ix_user_is_active", "is_active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password: Mapped[str] = mapped_column(String(255), nullable=False)  # 哈希密码
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # 状态信息
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # 时间信息
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    groups: Mapped[list["Group"]] = relationship("Group", secondary=user_groups, back_populates="users")
    site_groups: Mapped[list["SiteGroup"]] = relationship(
        "SiteGroup", secondary=user_site_groups, back_populates="members"
    )
    admin_site_groups: Mapped[list["SiteGroup"]] = relationship(
        "SiteGroup", secondary=site_group_admins, back_populates="admins"
    )
    profile: Mapped["UserProfile | None"] = relationship("UserProfile", back_populates="user", uselist=False)
    login_logs: Mapped[list["LoginLog"]] = relationship("LoginLog", back_populates="user")
    managed_hosts: Mapped[list["Host"]] = relationship(
        "Host", secondary="host_administrators", back_populates="administrators"
    )
    provider_hosts: Mapped[list["Host"]] = relationship(
        "Host", secondary="host_providers", back_populates="providers"
    )
    provider_hostgroups: Mapped[list["HostGroup"]] = relationship(
        "HostGroup", secondary="hostgroup_providers", back_populates="providers"
    )
    auto_product_groups: Mapped[list["ProductGroup"]] = relationship(
        "ProductGroup", secondary="productgroup_auto_assign_providers", back_populates="auto_assign_providers"
    )

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class UserProfile(Base):
    """用户资料模型"""
    __tablename__ = "user_profile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), unique=True, nullable=False)

    nickname: Mapped[str] = mapped_column(String(50), default="")
    gender: Mapped[str] = mapped_column(String(10), default="")
    birthday: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    location: Mapped[str] = mapped_column(String(100), default="")
    bio: Mapped[str] = mapped_column(Text, default="")

    # 通知设置
    email_notification: Mapped[bool] = mapped_column(Boolean, default=True)
    system_notification: Mapped[bool] = mapped_column(Boolean, default=True)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    user: Mapped["User"] = relationship("User", back_populates="profile")

    def __repr__(self) -> str:
        return f"<UserProfile {self.nickname or self.user_id}>"


class LoginLog(Base):
    """登录日志模型"""
    __tablename__ = "login_log"
    __table_args__ = (
        Index("ix_loginlog_user", "user_id"),
        Index("ix_loginlog_ip_address", "ip_address"),
        Index("ix_loginlog_status", "status"),
        Index("ix_loginlog_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, default="")
    login_type: Mapped[str] = mapped_column(String(20), default="web")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    user: Mapped["User | None"] = relationship("User", back_populates="login_logs")

    def __repr__(self) -> str:
        return f"<LoginLog {self.user_id} {self.ip_address}>"


class GroupProfile(Base):
    """用户组配置模型"""
    __tablename__ = "group_profile"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("group.id"), unique=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, default="")
    auto_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # relationships
    group: Mapped["Group"] = relationship("Group", back_populates="profile")

    def __repr__(self) -> str:
        return f"<GroupProfile {self.group_id}>"


class RegistrationLink(Base):
    """注册链接模型"""
    __tablename__ = "registration_link"
    __table_args__ = (
        Index("ix_reglink_created_at", "created_at"),
    )

    token: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id: Mapped[str] = mapped_column(String(36), ForeignKey("group.id"), nullable=False)
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")

    # relationships
    group: Mapped["Group"] = relationship("Group", back_populates="registration_links")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    used_by: Mapped["User | None"] = relationship("User", foreign_keys=[used_by_id])

    def __repr__(self) -> str:
        return f"<RegistrationLink {self.token[:8]}>"
