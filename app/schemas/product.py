"""
产品相关 Pydantic 模式

包含产品组、产品、开户申请、云电脑用户等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.host import HostBriefResponse


# ─── 产品组模式 ─────────────────────────────────────────────


class ProductGroupCreate(BaseModel):
    """创建产品组请求"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    display_order: int = 0
    is_active: bool = True
    visibility: str = Field(default="public", max_length=20)


class ProductGroupUpdate(BaseModel):
    """更新产品组请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    visibility: Optional[str] = Field(None, max_length=20)


class ProductGroupBriefResponse(BaseModel):
    """产品组简要响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    visibility: str = "public"


class ProductGroupResponse(BaseModel):
    """产品组响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str = ""
    display_order: int = 0
    is_active: bool = True
    visibility: str = "public"
    created_at: Optional[datetime] = None


# ─── 产品模式 ───────────────────────────────────────────────


class ProductCreate(BaseModel):
    """创建产品请求"""
    name: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    host_id: str
    product_group_id: Optional[str] = None
    rdp_port: int = Field(default=3389, ge=1, le=65535)
    display_hostname: str = Field(..., min_length=1, max_length=255)
    is_available: bool = True
    auto_approval: bool = False
    visibility: str = Field(default="public", max_length=20)
    enable_disk_quota: bool = False
    enable_host_protection: bool = False
    default_disk_quota: dict = {}
    allow_extra_quota_disks: list = []


class ProductUpdate(BaseModel):
    """更新产品请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    display_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    host_id: Optional[str] = None
    product_group_id: Optional[str] = None
    rdp_port: Optional[int] = Field(None, ge=1, le=65535)
    display_hostname: Optional[str] = Field(None, min_length=1, max_length=255)
    is_available: Optional[bool] = None
    auto_approval: Optional[bool] = None
    visibility: Optional[str] = Field(None, max_length=20)
    enable_disk_quota: Optional[bool] = None
    enable_host_protection: Optional[bool] = None
    default_disk_quota: Optional[dict] = None
    allow_extra_quota_disks: Optional[list] = None


class ProductResponse(BaseModel):
    """产品响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    display_name: str
    description: str = ""
    host: Optional[HostBriefResponse] = None
    product_group: Optional[ProductGroupBriefResponse] = None
    rdp_port: int = 3389
    display_hostname: str = ""
    is_available: bool = True
    auto_approval: bool = False
    visibility: str = "public"
    created_at: Optional[datetime] = None


# ─── 开户申请模式 ───────────────────────────────────────────


class AccountOpeningRequestCreate(BaseModel):
    """创建开户申请请求"""
    target_product_id: Optional[str] = None
    username: str = Field(..., min_length=1, max_length=150)
    user_fullname: str = Field(..., min_length=1, max_length=200)
    user_email: EmailStr
    user_description: str = ""
    contact_email: EmailStr
    contact_phone: Optional[str] = Field(None, max_length=20)
    requested_disk_capacity: dict = {}


class AccountOpeningRequestUpdate(BaseModel):
    """更新开户申请请求（审核操作）"""
    status: Optional[str] = Field(None, max_length=20)
    approval_notes: Optional[str] = None


class AccountOpeningRequestResponse(BaseModel):
    """开户申请响应（不含密码等敏感字段）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    applicant: Optional[dict] = None
    target_product: Optional[dict] = None
    username: str
    user_fullname: str
    status: str = "pending"
    result_message: str = ""
    created_at: Optional[datetime] = None


# ─── 云电脑用户模式 ─────────────────────────────────────────


class CloudComputerUserCreate(BaseModel):
    """创建云电脑用户请求"""
    username: str = Field(..., min_length=1, max_length=150)
    fullname: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    product_id: str
    is_admin: bool = False
    disk_quota: dict = {}


class CloudComputerUserUpdate(BaseModel):
    """更新云电脑用户请求"""
    fullname: Optional[str] = Field(None, min_length=1, max_length=200)
    email: Optional[EmailStr] = None
    status: Optional[str] = Field(None, max_length=20)
    is_admin: Optional[bool] = None
    disk_quota: Optional[dict] = None


class ProductBriefForCloudUser(BaseModel):
    """产品简要响应（用于云电脑用户嵌套）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    display_name: str


class CloudComputerUserResponse(BaseModel):
    """云电脑用户响应（不含密码等敏感字段）"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    fullname: str
    email: str
    product: Optional[ProductBriefForCloudUser] = None
    status: str = "active"
    is_admin: bool = False
    disk_quota: dict = {}
    created_at: Optional[datetime] = None
