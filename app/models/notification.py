"""站内信模型。

Notification 表示一条发送给某用户的站内信，按 site_group_id 隔离。
单表设计：每条记录独立归属用户，广播通过 service 层批量插入实现。

参考 PointRecord 的不可变流水模式：created_at 后内容不再变更，
仅 is_read / read_at 字段记录读取状态。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Notification(Base):
    """站内信主体。"""

    __tablename__ = "notification"
    __table_args__ = (
        # 用户未读数查询高频，按 (user_id, is_read) 建联合索引
        Index("ix_notification_user_read", "user_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── 收件人 ──
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ── 内容 ──
    # 类型：system / ticket / points / security / product / maintenance
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 等级：info / success / warning / error / brand
    level: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)        # 摘要（列表展示）
    body: Mapped[str | None] = mapped_column(Text, nullable=True)     # 详情（可选）
    # 预设图标名，留空则按 type 取默认图标
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # ── 关联与跳转 ──
    # ticket / cloud_computer / account_opening / product / point_record ...
    ref_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 点击跳转，如 /tickets/123
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── 已读状态 ──
    is_read: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── 站点隔离 ──
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
