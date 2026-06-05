"""
引导与令牌 Pydantic 模式

包含初始令牌、活动会话、证书配置令牌等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── 初始令牌模式 ───────────────────────────────────────────


class BootstrapPairRequest(BaseModel):
    """引导配对请求"""
    token: str = Field(..., min_length=1)
    pairing_code: str = Field(..., min_length=4, max_length=6)


class InitialTokenResponse(BaseModel):
    """初始令牌响应"""
    model_config = ConfigDict(from_attributes=True)

    token: str
    host_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    status: str = "ISSUED"
    pairing_code: Optional[str] = None
    pairing_code_expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ─── 活动会话模式 ───────────────────────────────────────────


class BootstrapSessionResponse(BaseModel):
    """引导会话响应"""
    session_token: str
    expires_at: Optional[datetime] = None


class ActiveSessionResponse(BaseModel):
    """活动会话响应"""
    model_config = ConfigDict(from_attributes=True)

    session_token: str
    host_id: str
    bound_ip: str
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ─── 证书配置令牌模式 ───────────────────────────────────────


class CertProvisionRequest(BaseModel):
    """证书配置请求"""
    token: str = Field(..., min_length=1)
    server_host: str = Field(..., min_length=1, max_length=255)
    hostname: str = Field(default="", max_length=255)
    ip_address: str = Field(default="", max_length=255)


class CertProvisionTokenResponse(BaseModel):
    """证书配置令牌响应"""
    model_config = ConfigDict(from_attributes=True)

    token: str
    host_id: Optional[str] = None
    server_host: str
    hostname: str = ""
    ip_address: str = ""
    expires_at: Optional[datetime] = None
    status: str = "ISSUED"
    created_by_id: Optional[str] = None
    consumed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
