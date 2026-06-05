"""
主题系统模型

包含 ThemeConfig, PageContent, WidgetLayout
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ThemeConfig(Base):
    """主题配置模型（单例）"""
    __tablename__ = "theme_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    active_theme: Mapped[str] = mapped_column(String(50), default="material-design-3", index=True)
    branding: Mapped[dict] = mapped_column(JSON, default=dict)
    custom_colors: Mapped[dict] = mapped_column(JSON, default=dict)
    css_overrides: Mapped[str] = mapped_column(Text, default="")
    enable_mobile_optimization: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ThemeConfig {self.active_theme}>"


class PageContent(Base):
    """可编辑页面内容模型"""
    __tablename__ = "page_content"
    __table_args__ = (
        Index("ix_pagecontent_position_enabled", "position", "is_enabled"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    position: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    page_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<PageContent {self.position}>"


class WidgetLayout(Base):
    """仪表盘组件布局配置模型"""
    __tablename__ = "widget_layout"
    __table_args__ = (
        Index("ix_widgetlayout_order_visible", "display_order", "is_visible"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    widget_type: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    column_span: Mapped[int] = mapped_column(SmallInteger, default=1)
    row_span: Mapped[int] = mapped_column(SmallInteger, default=1)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    responsive: Mapped[dict] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<WidgetLayout {self.widget_type}>"
