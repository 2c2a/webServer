"""
主题系统 Pydantic 模式

包含主题配置、页面内容、组件布局等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── 主题配置模式 ───────────────────────────────────────────


class ThemeConfigUpdate(BaseModel):
    """更新主题配置请求"""
    active_theme: Optional[str] = Field(None, max_length=50)
    branding: Optional[dict] = None
    custom_colors: Optional[dict] = None
    css_overrides: Optional[str] = None
    enable_mobile_optimization: Optional[bool] = None


class ThemeConfigResponse(BaseModel):
    """主题配置响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int = 1
    active_theme: str = "material-design-3"
    branding: dict = {}
    custom_colors: dict = {}
    css_overrides: str = ""
    enable_mobile_optimization: bool = True
    updated_at: Optional[datetime] = None


# ─── 页面内容模式 ───────────────────────────────────────────


class PageContentCreate(BaseModel):
    """创建页面内容请求"""
    position: str = Field(..., min_length=1, max_length=50)
    title: str = Field(default="", max_length=200)
    content: str = ""
    is_enabled: bool = True
    page_metadata: dict = {}


class PageContentUpdate(BaseModel):
    """更新页面内容请求"""
    position: Optional[str] = Field(None, min_length=1, max_length=50)
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    is_enabled: Optional[bool] = None
    page_metadata: Optional[dict] = None


class PageContentResponse(BaseModel):
    """页面内容响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: str
    title: str = ""
    content: str = ""
    is_enabled: bool = True
    page_metadata: dict = {}
    updated_at: Optional[datetime] = None


# ─── 组件布局模式 ───────────────────────────────────────────


class WidgetLayoutCreate(BaseModel):
    """创建组件布局请求"""
    widget_type: str = Field(..., min_length=1, max_length=50)
    display_order: int = 0
    column_span: int = Field(default=1, ge=1)
    row_span: int = Field(default=1, ge=1)
    is_visible: bool = True
    responsive: dict = {}


class WidgetLayoutUpdate(BaseModel):
    """更新组件布局请求"""
    widget_type: Optional[str] = Field(None, min_length=1, max_length=50)
    display_order: Optional[int] = None
    column_span: Optional[int] = Field(None, ge=1)
    row_span: Optional[int] = Field(None, ge=1)
    is_visible: Optional[bool] = None
    responsive: Optional[dict] = None


class WidgetLayoutResponse(BaseModel):
    """组件布局响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    widget_type: str
    display_order: int = 0
    column_span: int = 1
    row_span: int = 1
    is_visible: bool = True
    responsive: dict = {}
