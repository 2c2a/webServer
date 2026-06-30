"""公告模型。

Announcement 表示一条站点公告，展示在用户前台仪表盘。
按 site_group_id 隔离，支持置顶、启用/禁用、排序。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Announcement(Base, TimestampMixin):
    """公告模型。"""

    __tablename__ = "announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # ── 状态与展示 ──
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── 关联 ──
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── 关系 ──
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )
