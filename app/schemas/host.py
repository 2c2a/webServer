"""
主机相关 Pydantic 模式

包含主机、主机组等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── 主机请求模式 ───────────────────────────────────────────


class HostCreate(BaseModel):
    """创建主机请求"""
    name: str = Field(..., min_length=1, max_length=100)
    hostname: str = Field(..., min_length=1, max_length=255)
    connection_type: str = Field(default="winrm", max_length=20)
    auth_method: str = Field(default="ntlm", max_length=20)
    port: int = Field(default=5985, ge=1, le=65535)
    rdp_port: int = Field(default=3389, ge=1, le=65535)
    use_ssl: bool = False
    username: str = Field(default="", max_length=100)
    password: str = Field(default="", max_length=255)
    description: str = ""


class HostUpdate(BaseModel):
    """更新主机请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    hostname: Optional[str] = Field(None, min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    rdp_port: Optional[int] = Field(None, ge=1, le=65535)
    use_ssl: Optional[bool] = None
    username: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None


# ─── 主机响应模式 ───────────────────────────────────────────


class HostResponse(BaseModel):
    """主机响应（不含密码等敏感字段）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    os_type: str = "windows"
    hostname: str
    connection_type: str = "winrm"
    auth_method: str = "ntlm"
    port: int = 5985
    rdp_port: int = 3389
    use_ssl: bool = False
    username: str = ""
    status: str = "offline"
    description: str = ""
    tunnel_token: Optional[str] = None
    tunnel_status: str = "no_tunnel"
    cert_provision_status: str = "not_started"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HostBriefResponse(BaseModel):
    """主机简要响应（用于嵌套引用）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    hostname: str
    status: str = "offline"


# ─── 主机组请求模式 ─────────────────────────────────────────


class HostGroupCreate(BaseModel):
    """创建主机组请求"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""


class HostGroupUpdate(BaseModel):
    """更新主机组请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


# ─── 主机组响应模式 ─────────────────────────────────────────


class HostGroupResponse(BaseModel):
    """主机组响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str = ""
    hosts: list[HostBriefResponse] = []
    created_at: Optional[datetime] = None
