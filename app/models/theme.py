"""主题与页面内容模型。

ThemeConfig 为单例（id=1），存储全局主题、品牌资源与自定义 CSS。
PageContent 存储可编辑的页面内容片段（登录页、页脚等）。
已移除 WidgetLayout（仪表盘自定义功能已废弃）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ThemeConfig(Base):
    """主题配置（单例，id 固定 = 1）。

    存储全局主题设置、品牌资源路径与自定义 CSS 变量。
    """

    __tablename__ = "theme_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    active_theme: Mapped[str] = mapped_column(String(50), default="material-design-3")
    branding: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    custom_colors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    css_overrides: Mapped[str | None] = mapped_column(Text, nullable=True)
    enable_mobile_optimization: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PageContent(Base):
    """可编辑页面内容：按 position 标识存储页面文案片段。"""

    __tablename__ = "page_content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # "metadata" 是 SQLAlchemy Declarative API 保留字，Python 属性用 meta，DB 列名保持 metadata
    meta: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
