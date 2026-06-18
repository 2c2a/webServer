"""主机引导与证书配置令牌模型。

包含初始配置令牌（基于配对码认证）、活动会话与证书配置令牌。
这些模型用于主机首次接入与证书自动签发流程。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class InitialToken(Base):
    """初始配置令牌：基于配对码的简化主机认证机制。

    token 为主键（AccessToken），配对码 6 位数字，5 次尝试限制。
    """

    __tablename__ = "initial_token"

    token: Mapped[str] = mapped_column(String(255), primary_key=True)
    host_id: Mapped[int | None] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ISSUED")
    pairing_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    pairing_code_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pairing_attempts: Mapped[int] = mapped_column(Integer, default=0)
    cert_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    host: Mapped["Host | None"] = relationship(foreign_keys=[host_id])  # noqa: F821


class ActiveSession(Base):
    """活动会话：基于配对码认证的主机会话管理。"""

    __tablename__ = "active_session"

    session_token: Mapped[str] = mapped_column(String(255), primary_key=True)
    host_id: Mapped[int] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False
    )
    bound_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    host: Mapped["Host"] = relationship(foreign_keys=[host_id])  # noqa: F821


class CertProvisionToken(Base):
    """证书配置令牌：用于主机证书自动签发与配置流程。

    状态流转: ISSUED → HOSTNAME_UPLOADED → CERT_ISSUED → HOST_CONFIGURED → CONSUMED。
    """

    __tablename__ = "cert_provision_token"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    host_id: Mapped[int | None] = mapped_column(
        ForeignKey("hosts.id", ondelete="CASCADE"), nullable=True
    )
    server_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ISSUED")
    cert_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    host: Mapped["Host | None"] = relationship(foreign_keys=[host_id])  # noqa: F821
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )
