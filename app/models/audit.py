"""
审计日志模型

包含 AuditLog, SensitiveOperation, SecurityEvent, SessionActivity
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditLog(Base):
    """审计日志模型"""
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_auditlog_user_timestamp", "user_id", "timestamp"),
        Index("ix_auditlog_host_timestamp", "host_id", "timestamp"),
        Index("ix_auditlog_action_timestamp", "action", "timestamp"),
        Index("ix_auditlog_timestamp", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    host_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("host.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str] = mapped_column(Text, default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # relationships
    user: Mapped["User | None"] = relationship("User")
    host: Mapped["Host | None"] = relationship("Host")

    def __repr__(self) -> str:
        return f"<AuditLog {self.action}>"


class SensitiveOperation(Base):
    """敏感操作记录模型"""
    __tablename__ = "sensitive_operation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    operation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    approved_by: Mapped["User | None"] = relationship("User", foreign_keys=[approved_by_id])

    def __repr__(self) -> str:
        return f"<SensitiveOperation {self.operation_type}>"


class SecurityEvent(Base):
    """安全事件模型"""
    __tablename__ = "security_event"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    user: Mapped["User | None"] = relationship("User", foreign_keys=[user_id])
    resolved_by: Mapped["User | None"] = relationship("User", foreign_keys=[resolved_by_id])

    def __repr__(self) -> str:
        return f"<SecurityEvent {self.event_type} [{self.severity}]>"


class SessionActivity(Base):
    """会话活动记录模型"""
    __tablename__ = "session_activity"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"), nullable=False)
    session_key: Mapped[str] = mapped_column(String(40), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, default="")
    login_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    logout_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<SessionActivity {self.user_id}>"
