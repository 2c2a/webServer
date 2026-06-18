"""运营与产品模型。

包含公开主机信息、系统任务、产品组/产品、开户申请、云电脑用户、
RDP 域名路由、产品邀请令牌与产品访问授权。
RdpDomainRoute 已移除 tunnel_token 字段（隧道功能已废弃）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

# ──────────────────────────────────────────────
# 多对多关联表
# ──────────────────────────────────────────────

# 产品组 ↔ 自动分配提供商
productgroup_auto_providers = Table(
    "productgroup_auto_providers",
    Base.metadata,
    Column("productgroup_id", Integer, ForeignKey("product_group.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class PublicHostInfo(Base, TimestampMixin):
    """公开主机信息：在前端展示主机信息而不暴露敏感数据。"""

    __tablename__ = "public_host_info"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    internal_host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    display_rdp_port: Mapped[int] = mapped_column(Integer, default=3389)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── 关系 ──
    internal_host: Mapped["Host"] = relationship(  # noqa: F821
        foreign_keys=[internal_host_id]
    )


class SystemTask(Base):
    """系统任务：记录异步任务执行状态与结果。"""

    __tablename__ = "system_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── 关系 ──
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )


class ProductGroup(Base, TimestampMixin):
    """产品组：对产品进行分组管理。"""

    __tablename__ = "product_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── 关系 ──
    products: Mapped[list[Product]] = relationship(
        back_populates="product_group", lazy="selectin"
    )
    auto_assign_providers: Mapped[list["User"]] = relationship(  # noqa: F821
        secondary=productgroup_auto_providers,
        back_populates="auto_product_groups",
        lazy="selectin",
    )
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )


class Product(Base, TimestampMixin):
    """产品：面向用户的云电脑产品，关联到具体主机。"""

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    display_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_group.id", ondelete="SET NULL"), nullable=True
    )
    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False
    )
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True
    )
    rdp_port: Mapped[int] = mapped_column(Integer, default=3389)
    display_hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    limit_one_per_user: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_disk_quota: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_host_protection: Mapped[bool] = mapped_column(Boolean, default=False)
    default_disk_quota: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    allow_extra_quota_disks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── 关系 ──
    product_group: Mapped[ProductGroup | None] = relationship(
        back_populates="products", foreign_keys=[product_group_id]
    )
    host: Mapped["Host"] = relationship(foreign_keys=[host_id])  # noqa: F821
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )


class AccountOpeningRequest(Base, TimestampMixin):
    """开户申请：用户提交的云电脑开户请求。"""

    __tablename__ = "account_opening_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    applicant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    user_fullname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    user_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    requested_disk_capacity: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approval_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cloud_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── 关系 ──
    applicant: Mapped["User"] = relationship(foreign_keys=[applicant_id])  # noqa: F821
    target_product: Mapped[Product] = relationship(foreign_keys=[target_product_id])
    approved_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[approved_by_id]
    )


class CloudComputerUser(Base, TimestampMixin):
    """云电脑用户：在云电脑产品上创建的用户记录。

    initial_password_cipher 加密存储初始密码，阅后即焚。
    """

    __tablename__ = "cloud_computer_user"
    __table_args__ = (
        UniqueConstraint("product_id", "username", name="uq_cloud_user_product_username"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    fullname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    groups: Mapped[str | None] = mapped_column(Text, nullable=True)
    disk_quota: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_from_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_opening_request.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    initial_password_cipher: Mapped[str | None] = mapped_column(String(512), nullable=True)
    password_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    password_viewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── 关系 ──
    product: Mapped[Product] = relationship(foreign_keys=[product_id])
    created_from_request: Mapped[AccountOpeningRequest | None] = relationship(
        foreign_keys=[created_from_request_id]
    )
    owner: Mapped["User | None"] = relationship(foreign_keys=[owner_id])  # noqa: F821


class RdpDomainRoute(Base):
    """RDP 域名路由：分配给用户的临时 RDP 访问域名。

    tunnel_token 字段已移除（隧道功能已废弃）。
    """

    __tablename__ = "rdp_domain_route"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), nullable=False
    )
    assigned_to_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    product: Mapped[Product] = relationship(foreign_keys=[product_id])
    assigned_to: Mapped["User"] = relationship(foreign_keys=[assigned_to_id])  # noqa: F821


class ProductInvitationToken(Base):
    """产品邀请令牌：生成邀请链接以解锁产品或产品组的访问权限。"""

    __tablename__ = "product_invitation_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), nullable=True
    )
    product_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_group.id", ondelete="CASCADE"), nullable=True
    )
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    product: Mapped[Product | None] = relationship(foreign_keys=[product_id])
    product_group: Mapped[ProductGroup | None] = relationship(foreign_keys=[product_group_id])
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])  # noqa: F821


class ProductAccessGrant(Base):
    """产品访问授权：记录用户通过邀请链接获得的产品/产品组访问权限。"""

    __tablename__ = "product_access_grant"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_user_product_grant"),
        UniqueConstraint("user_id", "product_group_id", name="uq_user_productgroup_grant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("product.id", ondelete="CASCADE"), nullable=True
    )
    product_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_group.id", ondelete="CASCADE"), nullable=True
    )
    granted_by_token_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_invitation_token.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── 关系 ──
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821
    product: Mapped[Product | None] = relationship(foreign_keys=[product_id])
    product_group: Mapped[ProductGroup | None] = relationship(foreign_keys=[product_group_id])
    granted_by_token: Mapped[ProductInvitationToken | None] = relationship(
        foreign_keys=[granted_by_token_id]
    )
    revoked_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[revoked_by_id]
    )
