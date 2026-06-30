"""证书管理模型。

包含证书颁发机构（CA）、服务器证书与客户端证书。
CA 私钥不存数据库，仅存文件系统；数据库仅记录元数据与存储路径（cert_root/cert_sub）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CertificateAuthority(Base):
    """证书颁发机构（CA）。

    私钥不存 DB，存文件系统。cert_root/cert_sub 标识存储路径。
    """

    __tablename__ = "certificate_authority"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    cert_root: Mapped[str] = mapped_column(String(2), default="")
    cert_sub: Mapped[str] = mapped_column(String(2), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 关系 ──
    server_certificates: Mapped[list[ServerCertificate]] = relationship(
        back_populates="ca", cascade="all, delete-orphan"
    )
    client_certificates: Mapped[list[ClientCertificate]] = relationship(
        back_populates="ca", cascade="all, delete-orphan"
    )


class ServerCertificate(Base):
    """服务器证书：为主机签发的 TLS 服务器证书。"""

    __tablename__ = "server_certificate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ca_id: Mapped[int] = mapped_column(
        ForeignKey("certificate_authority.id", ondelete="CASCADE"), nullable=False
    )
    thumbprint: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revocation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revocation_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── 关系 ──
    ca: Mapped[CertificateAuthority] = relationship(back_populates="server_certificates")


class ClientCertificate(Base):
    """客户端证书：为用户签发的客户端认证证书。"""

    __tablename__ = "client_certificate"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    upn_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ca_id: Mapped[int] = mapped_column(
        ForeignKey("certificate_authority.id", ondelete="CASCADE"), nullable=False
    )
    thumbprint: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 关系 ──
    ca: Mapped[CertificateAuthority] = relationship(back_populates="client_certificates")
    assigned_to_user: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[assigned_to_user_id]
    )
