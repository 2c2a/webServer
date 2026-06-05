"""
用户相关 Pydantic 模式

包含用户注册、登录、信息更新、响应等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, EmailStr, Field, BaseModel

from app.schemas.common import APIResponse


# ─── 请求模式 ───────────────────────────────────────────────


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    phone: Optional[str] = Field(None, max_length=20)


class UserUpdate(BaseModel):
    """用户信息更新请求"""
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=20)
    avatar: Optional[str] = Field(None, max_length=500)


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenRefresh(BaseModel):
    """令牌刷新请求"""
    refresh_token: str


class PasswordChange(BaseModel):
    """修改密码请求"""
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class PasswordReset(BaseModel):
    """重置密码请求"""
    email: EmailStr


# ─── 响应模式 ───────────────────────────────────────────────


class UserResponse(BaseModel):
    """用户响应（不含密码等敏感字段）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    phone: Optional[str] = None
    avatar: Optional[str] = None
    is_verified: bool = False
    is_staff: bool = False
    is_superuser: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None


class UserBriefResponse(BaseModel):
    """用户简要响应（用于嵌套引用）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    avatar: Optional[str] = None


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


# ─── 组合响应 ───────────────────────────────────────────────


class LoginAPIResponse(APIResponse[LoginResponse]):
    """登录 API 响应"""
    pass


class UserAPIResponse(APIResponse[UserResponse]):
    """用户 API 响应"""
    pass
