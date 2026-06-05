"""
产品与运营模型

包含 ProductGroup, Product, AccountOpeningRequest, CloudComputerUser,
RdpDomainRoute, ProductInvitationToken, ProductAccessGrant, PublicHostInfo, SystemTask
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, SmallInteger, String, Table, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Many-to-many 关联表：产品组自动分配提供商
productgroup_auto_assign_providers = Table(
    "productgroup_auto_assign_providers",
    Base.metadata,
    Column("productgroup_id", String(36), ForeignKey("productgroup.id"), primary_key=True),
    Column("user_id", String(36), ForeignKey("user.id"), primary_key=True),
)


class ProductGroup(Base):
    """产品组模型"""
    __tablename__ = "productgroup"
    __table_args__ = (
        Index("ix_productgroup_is_active", "is_active"),
        Index("ix_productgroup_display_order", "display_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    visibility: Mapped[str] = mapped_column(String(20), default="public")

    # 外键
    site_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sitegroup.id"), nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    products: Mapped[list["Product"]] = relationship("Product", back_populates="product_group")
    auto_assign_providers: Mapped[list["User"]] = relationship(
        "User", secondary=productgroup_auto_assign_providers, back_populates="auto_product_groups"
    )
    site_group: Mapped["SiteGroup | None"] = relationship("SiteGroup")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"<ProductGroup {self.name}>"


class Product(Base):
    """产品模型"""
    __tablename__ = "product"
    __table_args__ = (
        Index("ix_product_is_available", "is_available"),
        Index("ix_product_host_id", "host_id"),
        Index("ix_product_created_at", "created_at"),
        Index("ix_product_created_by", "created_by_id"),
        Index("ix_product_product_group", "product_group_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_description: Mapped[str] = mapped_column(Text, default="")

    # 外键
    product_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("productgroup.id"), nullable=True)
    host_id: Mapped[str] = mapped_column(String(36), ForeignKey("host.id"), nullable=False)
    site_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sitegroup.id"), nullable=True)

    # 产品配置
    rdp_port: Mapped[int] = mapped_column(Integer, default=3389)
    display_hostname: Mapped[str] = mapped_column(String(255), nullable=False)

    # 产品状态
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(20), default="public")
    limit_one_per_user: Mapped[bool] = mapped_column(Boolean, default=False)

    # 磁盘配额与主机保护
    enable_disk_quota: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_host_protection: Mapped[bool] = mapped_column(Boolean, default=False)
    default_disk_quota: Mapped[dict] = mapped_column(JSON, default=dict)
    allow_extra_quota_disks: Mapped[dict] = mapped_column(JSON, default=list)

    # 创建者
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    product_group: Mapped["ProductGroup | None"] = relationship("ProductGroup", back_populates="products")
    host: Mapped["Host"] = relationship("Host")
    site_group: Mapped["SiteGroup | None"] = relationship("SiteGroup")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"<Product {self.display_name}>"


class AccountOpeningRequest(Base):
    """开户申请模型"""
    __tablename__ = "account_opening_request"
    __table_args__ = (
        Index("ix_aor_applicant", "applicant_id"),
        Index("ix_aor_status", "status"),
        Index("ix_aor_target_product", "target_product_id"),
        Index("ix_aor_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    applicant_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 开户信息
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    user_fullname: Mapped[str] = mapped_column(String(200), nullable=False)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False)
    user_description: Mapped[str] = mapped_column(Text, default="")

    # 目标产品
    target_product_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("product.id"), nullable=True)

    # 磁盘容量需求
    requested_disk_capacity: Mapped[dict] = mapped_column(JSON, default=dict)

    # 审核信息
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approved_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    approval_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_notes: Mapped[str] = mapped_column(Text, default="")

    # 结果信息
    cloud_user_id: Mapped[str] = mapped_column(String(255), default="")
    cloud_user_password: Mapped[str] = mapped_column(String(255), default="")  # 加密存储
    result_message: Mapped[str] = mapped_column(Text, default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    applicant: Mapped["User"] = relationship("User", foreign_keys=[applicant_id])
    target_product: Mapped["Product | None"] = relationship("Product")
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])

    def __repr__(self) -> str:
        return f"<AccountOpeningRequest {self.username}>"


class CloudComputerUser(Base):
    """云电脑用户模型"""
    __tablename__ = "cloud_computer_user"
    __table_args__ = (
        Index("ix_ccu_product", "product_id"),
        Index("ix_ccu_username", "username"),
        Index("ix_ccu_status", "status"),
        Index("ix_ccu_created_at", "created_at"),
        UniqueConstraint("product_id", "username", name="uq_ccu_product_username"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    fullname: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # 关联产品
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("product.id"), nullable=False)

    # 状态信息
    status: Mapped[str] = mapped_column(String(20), default="active")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    groups: Mapped[str] = mapped_column(Text, default="")

    # 磁盘配额
    disk_quota: Mapped[dict] = mapped_column(JSON, default=dict)

    # 创建信息
    created_from_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("account_opening_request.id"), nullable=True
    )
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)

    # 密码信息（加密存储）
    _initial_password: Mapped[str] = mapped_column("initial_password", String(512), default="")
    password_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    password_viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 时间信息
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    product: Mapped["Product"] = relationship("Product")
    created_from_request: Mapped["AccountOpeningRequest | None"] = relationship("AccountOpeningRequest")
    owner: Mapped["User | None"] = relationship("User", foreign_keys=[owner_id])

    def __repr__(self) -> str:
        return f"<CloudComputerUser {self.username}>"


class RdpDomainRoute(Base):
    """RDP域名路由模型"""
    __tablename__ = "rdp_domain_route"
    __table_args__ = (
        Index("ix_rdr_domain", "domain"),
        Index("ix_rdr_is_active", "is_active"),
        Index("ix_rdr_assigned_to", "assigned_to_id"),
        Index("ix_rdr_expires_at", "expires_at"),
        Index("ix_rdr_product", "product_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    domain: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    product_id: Mapped[str] = mapped_column(String(36), ForeignKey("product.id"), nullable=False)
    assigned_to_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    tunnel_token: Mapped[str] = mapped_column(String(64), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    product: Mapped["Product"] = relationship("Product")
    assigned_to: Mapped["User"] = relationship("User", foreign_keys=[assigned_to_id])

    def __repr__(self) -> str:
        return f"<RdpDomainRoute {self.domain}>"


class ProductInvitationToken(Base):
    """产品邀请令牌模型"""
    __tablename__ = "product_invitation_token"
    __table_args__ = (
        Index("ix_pit_token", "token"),
        Index("ix_pit_is_active", "is_active"),
        Index("ix_pit_expires_at", "expires_at"),
        Index("ix_pit_created_by", "created_by_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("product.id"), nullable=True)
    product_group_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("productgroup.id"), nullable=True
    )
    created_by_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    product: Mapped["Product | None"] = relationship("Product")
    product_group: Mapped["ProductGroup | None"] = relationship("ProductGroup")
    created_by: Mapped["User"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"<ProductInvitationToken {self.token[:8]}>"


class ProductAccessGrant(Base):
    """产品访问授权记录模型"""
    __tablename__ = "product_access_grant"
    __table_args__ = (
        Index("ix_pag_user", "user_id"),
        Index("ix_pag_product", "product_id"),
        Index("ix_pag_product_group", "product_group_id"),
        Index("ix_pag_is_revoked", "is_revoked"),
        Index("ix_pag_granted_at", "granted_at"),
        UniqueConstraint("user_id", "product_id", name="unique_user_product_grant"),
        UniqueConstraint("user_id", "product_group_id", name="unique_user_productgroup_grant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    product_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("product.id"), nullable=True)
    product_group_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("productgroup.id"), nullable=True
    )
    granted_by_token_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("product_invitation_token.id"), nullable=True
    )
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)

    # relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    product: Mapped["Product | None"] = relationship("Product")
    product_group: Mapped["ProductGroup | None"] = relationship("ProductGroup")
    granted_by_token: Mapped["ProductInvitationToken | None"] = relationship("ProductInvitationToken")
    revoked_by: Mapped["User | None"] = relationship("User", foreign_keys=[revoked_by_id])

    def __repr__(self) -> str:
        return f"<ProductAccessGrant {self.user_id}>"


class PublicHostInfo(Base):
    """公开主机信息模型"""
    __tablename__ = "public_host_info"
    __table_args__ = (
        Index("ix_phi_is_available", "is_available"),
        Index("ix_phi_internal_host", "internal_host_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    internal_host_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("host.id"), unique=True, nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_description: Mapped[str] = mapped_column(Text, default="")
    display_hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    display_rdp_port: Mapped[int] = mapped_column(Integer, default=3389)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    internal_host: Mapped["Host"] = relationship("Host")

    def __repr__(self) -> str:
        return f"<PublicHostInfo {self.display_name}>"


class SystemTask(Base):
    """系统任务模型"""
    __tablename__ = "system_task"
    __table_args__ = (
        Index("ix_st_status", "status"),
        Index("ix_st_task_type", "task_type"),
        Index("ix_st_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # relationships
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"<SystemTask {self.name}>"
