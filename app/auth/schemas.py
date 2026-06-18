"""认证 Pydantic schemas。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    # 前端 BLAKE2b 预哈希后的 hex（防 DoS 截断）
    password_prehash: str = Field(..., alias="password", min_length=8, max_length=256)
    captcha: str | None = None
    captcha_id: str | None = None


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=150, pattern=r"^[A-Za-z0-9._-]+$")
    password_prehash: str = Field(..., alias="password", min_length=8, max_length=256)
    email: str | None = None
    invite_token: str | None = None


class RefreshResponse(BaseModel):
    access_token: str
    expires_in: int


class LoginResponse(BaseModel):
    access_token: str
    expires_in: int
    username: str
    is_superuser: bool
    is_staff: bool


class UserInfo(BaseModel):
    id: int
    username: str
    email: str | None
    is_superuser: bool
    is_staff: bool
    is_verified: bool


class ChangePasswordRequest(BaseModel):
    old_password_prehash: str = Field(..., alias="old_password", min_length=8, max_length=256)
    new_password_prehash: str = Field(..., alias="new_password", min_length=8, max_length=256)
