"""
证书管理 Pydantic 模式

包含证书颁发机构、服务器证书、客户端证书等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── 证书颁发机构模式 ───────────────────────────────────────


class CertificateAuthorityCreate(BaseModel):
    """创建证书颁发机构请求"""
    name: str = Field(..., min_length=1, max_length=255)
    cert_root: str = Field(default="", max_length=2)
    cert_sub: str = Field(default="", max_length=2)
    description: Optional[str] = None


class CertificateAuthorityUpdate(BaseModel):
    """更新证书颁发机构请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    cert_root: Optional[str] = Field(None, max_length=2)
    cert_sub: Optional[str] = Field(None, max_length=2)
    is_active: Optional[bool] = None
    description: Optional[str] = None


class CertificateAuthorityResponse(BaseModel):
    """证书颁发机构响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    cert_root: str = ""
    cert_sub: str = ""
    is_active: bool = True
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class CertificateAuthorityBriefResponse(BaseModel):
    """证书颁发机构简要响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


# ─── 服务器证书模式 ─────────────────────────────────────────


class ServerCertificateCreate(BaseModel):
    """创建服务器证书请求"""
    hostname: str = Field(..., min_length=1, max_length=255)
    ip_address: Optional[str] = Field(None, max_length=45)
    ca_id: str
    thumbprint: str = Field(..., min_length=1, max_length=255)


class ServerCertificateResponse(BaseModel):
    """服务器证书响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    hostname: str
    ip_address: Optional[str] = None
    ca_id: str
    ca: Optional[CertificateAuthorityBriefResponse] = None
    thumbprint: str
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    is_revoked: bool = False
    revocation_reason: Optional[str] = None
    revocation_date: Optional[datetime] = None


# ─── 客户端证书模式 ─────────────────────────────────────────


class ClientCertificateCreate(BaseModel):
    """创建客户端证书请求"""
    name: str = Field(..., min_length=1, max_length=255)
    upn_value: str = Field(default="", max_length=255)
    ca_id: str
    thumbprint: str = Field(..., min_length=1, max_length=255)
    assigned_to_user_id: Optional[str] = None
    description: Optional[str] = None


class ClientCertificateUpdate(BaseModel):
    """更新客户端证书请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    upn_value: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    description: Optional[str] = None


class ClientCertificateResponse(BaseModel):
    """客户端证书响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    upn_value: str = ""
    ca_id: str
    ca: Optional[CertificateAuthorityBriefResponse] = None
    thumbprint: str
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    assigned_to_user_id: Optional[str] = None
    is_active: bool = True
    description: Optional[str] = None
