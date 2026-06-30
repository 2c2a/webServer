"""工单系统模型。

包含工单分类、工单主体、评论、活动记录与附件。
工单可关联云电脑用户和开户申请，支持自动分配、SLA 时限与满意度评价。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class TicketCategory(Base, TimestampMixin):
    """工单分类：定义工单的分组、默认优先级、自动分配与 SLA。"""

    __tablename__ = "ticket_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    default_priority: Mapped[str] = mapped_column(String(20), default="normal")
    auto_assign_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    auto_assign_to_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_group.id", ondelete="SET NULL"), nullable=True
    )
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_banned_users: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── 关系 ──
    tickets: Mapped[list[Ticket]] = relationship(back_populates="category")
    auto_assign_to: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[auto_assign_to_id]
    )
    auto_assign_to_group: Mapped["UserGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[auto_assign_to_group_id]
    )
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )


class Ticket(Base, TimestampMixin):
    """工单主体。"""

    __tablename__ = "ticket"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("ticket_category.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="open")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    source: Mapped[str] = mapped_column(String(20), default="web")
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assigned_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_group.id", ondelete="SET NULL"), nullable=True
    )
    related_cloud_computer_id: Mapped[int | None] = mapped_column(
        ForeignKey("cloud_computer_user.id", ondelete="SET NULL"), nullable=True
    )
    related_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("account_opening_request.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    satisfaction_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True
    )

    # ── 关系 ──
    category: Mapped[TicketCategory | None] = relationship(
        back_populates="tickets", foreign_keys=[category_id]
    )
    creator: Mapped["User"] = relationship(foreign_keys=[creator_id])  # noqa: F821
    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_id])  # noqa: F821
    assigned_group: Mapped["UserGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[assigned_group_id]
    )
    related_cloud_computer: Mapped["CloudComputerUser | None"] = relationship(  # noqa: F821
        foreign_keys=[related_cloud_computer_id]
    )
    related_request: Mapped["AccountOpeningRequest | None"] = relationship(  # noqa: F821
        foreign_keys=[related_request_id]
    )
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
    comments: Mapped[list[TicketComment]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", lazy="selectin"
    )
    activities: Mapped[list[TicketActivity]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", lazy="selectin"
    )
    attachments: Mapped[list[TicketAttachment]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", lazy="selectin"
    )


class TicketComment(Base):
    """工单评论/回复。"""

    __tablename__ = "ticket_comment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    ticket: Mapped[Ticket] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship(foreign_keys=[author_id])  # noqa: F821


class TicketActivity(Base):
    """工单活动记录：状态变更、分配、评论等操作的审计轨迹。"""

    __tablename__ = "ticket_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    ticket: Mapped[Ticket] = relationship(back_populates="activities")
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_id])  # noqa: F821


class TicketAttachment(Base):
    """工单附件。"""

    __tablename__ = "ticket_attachment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("ticket.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    ticket: Mapped[Ticket] = relationship(back_populates="attachments")
    uploaded_by: Mapped["User"] = relationship(foreign_keys=[uploaded_by_id])  # noqa: F821
