"""
工单系统 Pydantic 模式

包含工单分类、工单、工单评论等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.user import UserBriefResponse


# ─── 工单分类模式 ───────────────────────────────────────────


class TicketCategoryCreate(BaseModel):
    """创建工单分类请求"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    icon: str = Field(default="help_outline", max_length=50)
    default_priority: str = Field(default="medium", max_length=20)
    auto_assign_to_id: Optional[str] = None
    auto_assign_to_group_id: Optional[str] = None
    sla_hours: int = Field(default=24, ge=1)
    is_active: bool = True
    display_order: int = 0


class TicketCategoryUpdate(BaseModel):
    """更新工单分类请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = Field(None, max_length=50)
    default_priority: Optional[str] = Field(None, max_length=20)
    auto_assign_to_id: Optional[str] = None
    auto_assign_to_group_id: Optional[str] = None
    sla_hours: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class TicketCategoryResponse(BaseModel):
    """工单分类响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str = ""
    icon: str = "help_outline"
    default_priority: str = "medium"
    sla_hours: int = 24
    is_active: bool = True
    display_order: int = 0
    created_at: Optional[datetime] = None


class TicketCategoryBriefResponse(BaseModel):
    """工单分类简要响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str


# ─── 工单模式 ───────────────────────────────────────────────


class TicketCreate(BaseModel):
    """创建工单请求"""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    category_id: Optional[str] = None
    priority: str = Field(default="medium", max_length=20)
    related_product_id: Optional[str] = None
    related_host_id: Optional[str] = None


class TicketUpdate(BaseModel):
    """更新工单请求"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category_id: Optional[str] = None
    priority: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=20)
    assignee_id: Optional[str] = None
    assigned_group_id: Optional[str] = None


class TicketResponse(BaseModel):
    """工单响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    ticket_no: str
    title: str
    description: str
    category: Optional[TicketCategoryBriefResponse] = None
    status: str = "pending"
    priority: str = "medium"
    creator: Optional[UserBriefResponse] = None
    assignee: Optional[UserBriefResponse] = None
    created_at: Optional[datetime] = None


# ─── 工单评论模式 ───────────────────────────────────────────


class TicketCommentCreate(BaseModel):
    """创建工单评论请求"""
    content: str = Field(..., min_length=1)
    is_internal: bool = False


class TicketCommentResponse(BaseModel):
    """工单评论响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    author: Optional[UserBriefResponse] = None
    content: str
    is_internal: bool = False
    created_at: Optional[datetime] = None
