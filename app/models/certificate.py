"""
证书管理模型

包含 CertificateAuthority, ServerCertificate, ClientCertificate
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CertificateAuthority(Base):
    """证书颁发机构模型"""
    __tablename__ = "certificate_authority"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    cert_root: Mapped[str] = mapped_column(String(2), default="")
    cert_sub: Mapped[str] = mapped_column(String(2), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    server_certificates: Mapped[list["ServerCertificate"]] = relationship(
        "ServerCertificate", back_populates="ca"
    )
    client_certificates: Mapped[list["ClientCertificate"]] = relationship(
        "ClientCertificate", back_populates="ca"
    )

    def __repr__(self) -> str:
        return f"<CertificateAuthority {self.name}>"


class ServerCertificate(Base):
    """服务器证书模型"""
    __tablename__ = "server_certificate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hostname: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ca_id: Mapped[str] = mapped_column(String(36), ForeignKey("certificate_authority.id"), nullable=False)
    thumbprint: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    revocation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revocation_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # relationships
    ca: Mapped["CertificateAuthority"] = relationship(
        "CertificateAuthority", back_populates="server_certificates"
    )

    def __repr__(self) -> str:
        return f"<ServerCertificate {self.hostname}>"


class ClientCertificate(Base):
    """客户端证书模型"""
    __tablename__ = "client_certificate"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    upn_value: Mapped[str] = mapped_column(String(255), default="")
    ca_id: Mapped[str] = mapped_column(String(36), ForeignKey("certificate_authority.id"), nullable=False)
    thumbprint: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # relationships
    ca: Mapped["CertificateAuthority"] = relationship(
        "CertificateAuthority", back_populates="client_certificates"
    )
    assigned_to_user: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<ClientCertificate {self.name}>"
