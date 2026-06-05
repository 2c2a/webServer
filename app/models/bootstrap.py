"""
引导与令牌模型

包含 InitialToken, ActiveSession, CertProvisionToken
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InitialToken(Base):
    """初始配置令牌模型 - 基于配对码的简化认证机制"""
    __tablename__ = "initial_token"

    token: Mapped[str] = mapped_column(String(255), primary_key=True)
    host_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("host.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ISSUED")
    pairing_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    pairing_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pairing_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    cert_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # relationships
    host: Mapped["Host | None"] = relationship("Host")

    def __repr__(self) -> str:
        return f"<InitialToken {self.token[:8]}>"


class ActiveSession(Base):
    """活动会话模型 - 基于配对码认证的会话管理"""
    __tablename__ = "active_session"

    session_token: Mapped[str] = mapped_column(String(255), primary_key=True)
    host_id: Mapped[str] = mapped_column(String(36), ForeignKey("host.id"), nullable=False)
    bound_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    host: Mapped["Host"] = relationship("Host")

    def __repr__(self) -> str:
        return f"<ActiveSession {self.session_token[:8]}>"


class CertProvisionToken(Base):
    """证书配置令牌模型"""
    __tablename__ = "cert_provision_token"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    host_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("host.id"), nullable=True)
    server_host: Mapped[str] = mapped_column(String(255), nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    ip_address: Mapped[str] = mapped_column(String(255), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ISSUED")
    cert_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    host: Mapped["Host | None"] = relationship("Host")
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])

    def __repr__(self) -> str:
        return f"<CertProvisionToken {self.token[:8]}>"
