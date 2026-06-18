"""用户与认证模型。

包含用户主表、多邮箱、资料、封禁/封禁历史、登录日志、注册链接、用户组，
以及用户-站点组、用户-用户组的多对多关联表。
所有敏感字段使用 _cipher 后缀，不存明文。
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
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

# 用户 ↔ 站点组（成员关系）
user_site_groups = Table(
    "user_site_groups",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("site_group_id", Integer, ForeignKey("site_group.id", ondelete="CASCADE"), primary_key=True),
)

# 用户 ↔ 站点组（管理员关系）
user_site_group_admins = Table(
    "user_site_group_admins",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("site_group_id", Integer, ForeignKey("site_group.id", ondelete="CASCADE"), primary_key=True),
)

# 用户 ↔ 用户组
user_group_members = Table(
    "user_group_members",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("user_group.id", ondelete="CASCADE"), primary_key=True),
)


class UserGroup(Base):
    """用户组（替代 Django Group）。

    支持默认组、自动赋予 staff 身份、排序等配置。
    """

    __tablename__ = "user_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    auto_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # ── 关系 ──
    users: Mapped[list[User]] = relationship(  # noqa: F821
        secondary=user_group_members,
        back_populates="groups",
        lazy="selectin",
    )


class User(Base, TimestampMixin):
    """用户主表。

    password_hash 存储 Argon2id PHC 字符串；ban_version 用于无状态令牌撤销。
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── 状态标记 ──
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 登录信息 ──
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    # ── 无状态令牌撤销 ──
    ban_version: Mapped[int] = mapped_column(Integer, default=0)

    # ── 注册时间 ──
    date_joined: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    emails: Mapped[list[UserEmail]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
    profile: Mapped[UserProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    active_ban: Mapped[UserBan | None] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[UserBan.user_id]",
    )

    # 站点组成员关系（M2M → user_site_groups）
    site_groups: Mapped[list["SiteGroup"]] = relationship(  # noqa: F821
        secondary="user_site_groups",
        back_populates="members",
        lazy="selectin",
    )
    # 站点组管理员关系（M2M → user_site_group_admins）
    admin_site_groups: Mapped[list["SiteGroup"]] = relationship(  # noqa: F821
        secondary="user_site_group_admins",
        back_populates="admins",
        lazy="selectin",
    )
    # 用户组（M2M → user_group_members）
    groups: Mapped[list[UserGroup]] = relationship(
        secondary=user_group_members,
        back_populates="users",
        lazy="selectin",
    )

    # 主机授权管理员（M2M → host_administrators，反向 Host.administrators）
    managed_hosts: Mapped[list["Host"]] = relationship(  # noqa: F821
        secondary="host_administrators",
        back_populates="administrators",
        lazy="selectin",
    )
    # 主机管理提供商（M2M → host_providers，反向 Host.providers）
    provider_hosts: Mapped[list["Host"]] = relationship(  # noqa: F821
        secondary="host_providers",
        back_populates="providers",
        lazy="selectin",
    )
    # 主机组管理提供商（M2M → hostgroup_providers，反向 HostGroup.providers）
    provider_hostgroups: Mapped[list["HostGroup"]] = relationship(  # noqa: F821
        secondary="hostgroup_providers",
        back_populates="providers",
        lazy="selectin",
    )
    # 产品组自动分配提供商（M2M → productgroup_auto_providers，反向 ProductGroup.auto_assign_providers）
    auto_product_groups: Mapped[list["ProductGroup"]] = relationship(  # noqa: F821
        secondary="productgroup_auto_providers",
        back_populates="auto_assign_providers",
        lazy="selectin",
    )


class UserEmail(Base):
    """用户多邮箱绑定。

    一个用户可有一个主邮箱和多个子邮箱，用于账户合并检测与封禁污染追踪。
    """

    __tablename__ = "user_email"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    user: Mapped[User] = relationship(back_populates="emails")


class UserProfile(Base, TimestampMixin):
    """用户资料（OneToOne → User）。"""

    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_notification: Mapped[bool] = mapped_column(Boolean, default=True)
    system_notification: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── 关系 ──
    user: Mapped[User] = relationship(back_populates="profile")


class UserBan(Base):
    """用户封禁记录（OneToOne → User）。

    自定义封禁系统，替代 is_active 字段。一个用户同一时间只能有一条活跃封禁。
    """

    __tablename__ = "user_ban"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    banned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    user: Mapped[User] = relationship(back_populates="active_ban", foreign_keys=[user_id])
    banned_by: Mapped[User | None] = relationship(foreign_keys=[banned_by_id])


class UserBanHistory(Base):
    """封禁历史记录。

    解封时将活跃封禁归档到此表，保留完整封禁历史。
    """

    __tablename__ = "user_ban_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    banned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    unbanned_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    banned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    unbanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── 关系 ──
    user: Mapped[User] = relationship(foreign_keys=[user_id])
    banned_by: Mapped[User | None] = relationship(foreign_keys=[banned_by_id])
    unbanned_by: Mapped[User | None] = relationship(foreign_keys=[unbanned_by_id])


class LoginLog(Base):
    """登录日志。"""

    __tablename__ = "login_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, default="")
    login_type: Mapped[str] = mapped_column(String(20), default="web")
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    user: Mapped[User | None] = relationship(foreign_keys=[user_id])


class RegistrationLink(Base):
    """注册链接。

    通过此链接注册的用户将自动加入指定用户组。
    """

    __tablename__ = "registration_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    group_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_group.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    used_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    group: Mapped[UserGroup | None] = relationship(foreign_keys=[group_id])
    created_by: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    used_by: Mapped[User | None] = relationship(foreign_keys=[used_by_id])
