"""审计与安全模型。

包含审计日志、敏感操作记录、安全事件与会话活动。
AuditLog 使用 JSON details + content_type/object_id 字符串替代 Django GenericForeignKey，
避免引入 ContentType 框架的复杂度。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AuditLog(Base):
    """审计日志：记录用户操作、主机操作等全量审计轨迹。

    使用 JSON details 存储操作详情，content_type + object_id 字符串引用关联对象，
    替代 Django 的 GenericForeignKey 机制。
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True
    )
    host_id: Mapped[int | None] = mapped_column(
        ForeignKey("hosts.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── 关系 ──
    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])  # noqa: F821
    host: Mapped["Host | None"] = relationship(foreign_keys=[host_id])  # noqa: F821


class SensitiveOperation(Base):
    """敏感操作记录：需审批的高风险操作审计。"""

    __tablename__ = "sensitive_operation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 关系 ──
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821
    approved_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[approved_by_id]
    )


class SecurityEvent(Base):
    """安全事件：记录未授权访问、暴力破解等安全告警。"""

    __tablename__ = "security_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 关系 ──
    user: Mapped["User | None"] = relationship(foreign_keys=[user_id])  # noqa: F821
    resolved_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[resolved_by_id]
    )


class SessionActivity(Base):
    """会话活动记录：跟踪用户登录会话状态。"""

    __tablename__ = "session_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    session_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, default="")
    login_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    logout_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── 关系 ──
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821
