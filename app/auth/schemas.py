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
    email: str = Field(..., min_length=3, max_length=254)
    email_code: str = Field(..., min_length=4, max_length=16)
    invite_token: str | None = None
    captcha: str | None = None
    captcha_id: str | None = None


class SendEmailCodeRequest(BaseModel):
    """发送注册邮箱验证码请求。

    要求前端先通过行为验证码（scene='email'），
    后端二次校验通过后才允许发送邮箱验证码。
    """

    email: str = Field(..., min_length=3, max_length=254)
    captcha: str | None = None
    captcha_id: str | None = None


class SendEmailCodeResponse(BaseModel):
    """发送验证码响应。

    - 成功：``sent=True`` + ``expires_in``（剩余有效期秒）
    - 频率限制：``sent=False`` + ``resend_in``（距下次可发送秒数）
    - SMTP 未配置：``sent=False`` + ``dev_code``（dev 回退，仅 DEBUG 下）
    """

    sent: bool
    expires_in: int = 0
    resend_in: int = 0
    dev_code: str | None = None


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


class ForgotPasswordRequest(BaseModel):
    """忘记密码 - 自助重置第一步：用户名 + 注册邮箱 + 行为验证码校验。

    校验通过后：
    - 若 SMTP 已配置：向邮箱发送含重置链接的邮件，返回通用「邮件已发送」响应
      （不泄漏邮箱是否匹配账号，防止枚举）
    - 若 SMTP 未配置（dev）：返回 reset_token 供前端直接进入重置步骤
    """

    username: str = Field(..., min_length=1, max_length=150)
    email: str = Field(..., min_length=3, max_length=254)
    captcha: str | None = None
    captcha_id: str | None = None


class ForgotPasswordResponse(BaseModel):
    """忘记密码响应。

    `email_sent=True` 表示邮件已发送（生产/SMTP 已配置），
    此时 `reset_token` 为空，用户需查收邮件。
    `email_sent=False` 表示 SMTP 未配置（dev 回退），
    `reset_token` 直接返回供前端进入重置步骤。
    """

    email_sent: bool = False
    reset_token: str | None = None
    expires_in: int  # 令牌剩余有效期（秒）


class ResetPasswordRequest(BaseModel):
    """忘记密码 - 自助重置第二步：凭重置令牌设置新密码。"""

    reset_token: str
    new_password_prehash: str = Field(..., alias="new_password", min_length=8, max_length=256)
