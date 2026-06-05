"""
仪表盘与系统配置 Pydantic 模式

包含系统配置、站点组、仪表盘组件等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ─── 系统配置模式 ───────────────────────────────────────────


class SystemConfigUpdate(BaseModel):
    """更新系统配置请求"""
    # SMTP 配置
    smtp_host: Optional[str] = Field(None, max_length=255)
    smtp_port: Optional[int] = Field(None, ge=1, le=65535)
    smtp_use_tls: Optional[bool] = None
    smtp_username: Optional[str] = Field(None, max_length=255)
    smtp_password: Optional[str] = Field(None, max_length=255)
    smtp_from_email: Optional[EmailStr] = None

    # 验证码配置
    captcha_provider: Optional[str] = Field(None, max_length=32)
    captcha_type: Optional[str] = Field(None, max_length=32)

    # 站点配置
    site_name: Optional[str] = Field(None, max_length=100)
    enable_registration: Optional[bool] = None
    icp_number: Optional[str] = Field(None, max_length=100)
    police_number: Optional[str] = Field(None, max_length=100)
    email_suffix_whitelist: Optional[str] = None
    email_suffix_blacklist: Optional[str] = None
    local_access_locked: Optional[bool] = None
    hostname_branding: Optional[dict] = None


class SystemConfigResponse(BaseModel):
    """系统配置响应（密码字段脱敏）"""
    model_config = ConfigDict(from_attributes=True)

    id: int = 1

    # SMTP 配置
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_use_tls: bool = True
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None  # 响应时脱敏为 "******"
    smtp_from_email: Optional[str] = None

    # 验证码配置
    captcha_provider: str = "none"
    captcha_type: str = "SLIDER"

    # 站点配置
    site_name: str = "2c2a"
    enable_registration: bool = False
    icp_number: Optional[str] = None
    police_number: Optional[str] = None
    email_suffix_whitelist: Optional[str] = None
    email_suffix_blacklist: Optional[str] = None
    local_access_locked: bool = False
    hostname_branding: dict = {}

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """自动脱敏密码字段"""
        if obj is not None and hasattr(obj, "smtp_password") and obj.smtp_password:
            obj.smtp_password = "******"
        return super().model_validate(obj, **kwargs)


# ─── 站点组模式 ─────────────────────────────────────────────


class SiteGroupCreate(BaseModel):
    """创建站点组请求"""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    site_name: str = Field(default="", max_length=100)
    site_icon: str = Field(default="", max_length=500)
    is_active: bool = True


class SiteGroupUpdate(BaseModel):
    """更新站点组请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    site_name: Optional[str] = Field(None, max_length=100)
    site_icon: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class SiteGroupResponse(BaseModel):
    """站点组响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str = ""
    site_name: str = ""
    site_icon: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None


# ─── 仪表盘组件模式 ─────────────────────────────────────────


class DashboardWidgetCreate(BaseModel):
    """创建仪表盘组件请求"""
    widget_type: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=200)
    display_order: int = 0
    is_enabled: bool = True
    widget_config: dict = {}


class DashboardWidgetUpdate(BaseModel):
    """更新仪表盘组件请求"""
    widget_type: Optional[str] = Field(None, min_length=1, max_length=50)
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    display_order: Optional[int] = None
    is_enabled: Optional[bool] = None
    widget_config: Optional[dict] = None


class DashboardWidgetResponse(BaseModel):
    """仪表盘组件响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    widget_type: str
    title: str
    display_order: int = 0
    is_enabled: bool = True
    widget_config: dict = {}
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
