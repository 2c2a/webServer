"""
审计日志 Pydantic 模式

包含审计日志、敏感操作、安全事件、会话活动等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserBriefResponse


# ─── 审计日志模式 ───────────────────────────────────────────


class AuditLogResponse(BaseModel):
    """审计日志响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str] = None
    user: Optional[UserBriefResponse] = None
    host_id: Optional[str] = None
    action: str
    ip_address: Optional[str] = None
    user_agent: str = ""
    timestamp: Optional[datetime] = None
    success: bool = True
    details: dict = {}
    result: Optional[str] = None
    content_type: Optional[str] = None
    object_id: Optional[int] = None


class AuditLogQuery(BaseModel):
    """审计日志查询参数"""
    user_id: Optional[str] = None
    host_id: Optional[str] = None
    action: Optional[str] = Field(None, max_length=50)
    success: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


# ─── 敏感操作模式 ───────────────────────────────────────────


class SensitiveOperationResponse(BaseModel):
    """敏感操作响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    operation_type: str
    user_id: str
    user: Optional[UserBriefResponse] = None
    target: str
    timestamp: Optional[datetime] = None
    ip_address: str
    justification: str
    approved_by_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    result: Optional[str] = None


# ─── 安全事件模式 ───────────────────────────────────────────


class SecurityEventResponse(BaseModel):
    """安全事件响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    severity: str = "medium"
    user_id: Optional[str] = None
    user: Optional[UserBriefResponse] = None
    ip_address: str
    description: str
    timestamp: Optional[datetime] = None
    resolved: bool = False
    resolved_by_id: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None


# ─── 会话活动模式 ───────────────────────────────────────────


class SessionActivityResponse(BaseModel):
    """会话活动响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    user: Optional[UserBriefResponse] = None
    session_key: str
    ip_address: str
    user_agent: str = ""
    login_time: Optional[datetime] = None
    logout_time: Optional[datetime] = None
    is_active: bool = True
