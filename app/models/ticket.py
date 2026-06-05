"""
工单系统模型

包含 TicketCategory, Ticket, TicketComment, TicketActivity, TicketAttachment
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TicketCategory(Base):
    """工单分类模型"""
    __tablename__ = "ticket_category"
    __table_args__ = (
        Index("ix_ticketcategory_is_active", "is_active"),
        Index("ix_ticketcategory_display_order", "display_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(50), default="help_outline")
    default_priority: Mapped[str] = mapped_column(String(20), default="medium")
    auto_assign_to_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    auto_assign_to_group_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("group.id"), nullable=True
    )
    sla_hours: Mapped[int] = mapped_column(Integer, default=24)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="category")
    auto_assign_to: Mapped["User | None"] = relationship("User", foreign_keys=[auto_assign_to_id])
    auto_assign_to_group: Mapped["Group | None"] = relationship("Group", foreign_keys=[auto_assign_to_group_id])
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"<TicketCategory {self.name}>"


class Ticket(Base):
    """工单模型"""
    __tablename__ = "ticket"
    __table_args__ = (
        Index("ix_ticket_ticket_no", "ticket_no"),
        Index("ix_ticket_status", "status"),
        Index("ix_ticket_priority", "priority"),
        Index("ix_ticket_assignee", "assignee_id"),
        Index("ix_ticket_assigned_group", "assigned_group_id"),
        Index("ix_ticket_creator", "creator_id"),
        Index("ix_ticket_category", "category_id"),
        Index("ix_ticket_created_at", "created_at"),
        Index("ix_ticket_due_at", "due_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # 外键
    category_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ticket_category.id"), nullable=True
    )
    creator_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    assigned_group_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("group.id"), nullable=True)
    related_product_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("product.id"), nullable=True)
    related_host_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("host.id"), nullable=True)

    # 状态与优先级
    status: Mapped[str] = mapped_column(String(20), default="pending")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    source: Mapped[str] = mapped_column(String(20), default="web")

    # 时间信息
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 满意度
    satisfaction: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    satisfaction_comment: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    category: Mapped["TicketCategory | None"] = relationship("TicketCategory", back_populates="tickets")
    creator: Mapped["User"] = relationship("User", foreign_keys=[creator_id])
    assignee: Mapped["User | None"] = relationship("User", foreign_keys=[assignee_id])
    assigned_group: Mapped["Group | None"] = relationship("Group", foreign_keys=[assigned_group_id])
    related_product: Mapped["Product | None"] = relationship("Product")
    related_host: Mapped["Host | None"] = relationship("Host")
    comments: Mapped[list["TicketComment"]] = relationship("TicketComment", back_populates="ticket")
    activities: Mapped[list["TicketActivity"]] = relationship("TicketActivity", back_populates="ticket")
    attachments: Mapped[list["TicketAttachment"]] = relationship("TicketAttachment", back_populates="ticket")

    def __repr__(self) -> str:
        return f"<Ticket [{self.ticket_no}] {self.title}>"


class TicketComment(Base):
    """工单评论/回复模型"""
    __tablename__ = "ticket_comment"
    __table_args__ = (
        Index("ix_ticketcomment_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("ticket.id"), nullable=False)
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="comments")
    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])

    def __repr__(self) -> str:
        return f"<TicketComment {self.id}>"


class TicketActivity(Base):
    """工单活动记录模型"""
    __tablename__ = "ticket_activity"
    __table_args__ = (
        Index("ix_ticketactivity_ticket_created", "ticket_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("ticket.id"), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    old_value: Mapped[str] = mapped_column(String(255), default="")
    new_value: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="activities")
    actor: Mapped["User | None"] = relationship("User", foreign_keys=[actor_id])

    def __repr__(self) -> str:
        return f"<TicketActivity {self.action}>"


class TicketAttachment(Base):
    """工单附件模型"""
    __tablename__ = "ticket_attachment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id: Mapped[str] = mapped_column(String(36), ForeignKey("ticket.id"), nullable=False)
    file: Mapped[str] = mapped_column(String(500), nullable=False)  # 存储文件路径，非 FileField
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    uploaded_by_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="attachments")
    uploaded_by: Mapped["User"] = relationship("User", foreign_keys=[uploaded_by_id])

    def __repr__(self) -> str:
        return f"<TicketAttachment {self.filename}>"
