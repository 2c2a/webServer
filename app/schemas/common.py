"""
通用 Pydantic 模式

包含 API 响应、分页等通用模式
"""
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """通用 API 响应模式"""
    success: bool = True
    message: str = ""
    data: Optional[T] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应模式"""
    success: bool = True
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: list[T] = []


class PaginationParams(BaseModel):
    """分页请求参数"""
    page: int = 1
    page_size: int = 20
