"""积分系统模型。

包含积分任务配置、积分明细流水与用户积分余额。

* :class:`PointTask`：管理员配置的积分任务，带 ``detection_method`` 字段
  标识任务完成检测方式（如 ``daily_checkin`` / ``ticket_submit``，更多方式
  可通过插件注册到 :mod:`app.points.registry`）；
* :class:`PointRecord`：积分明细流水，每次变动写一条不可变记录；
* :class:`UserPoints`：用户在某站点组下的积分余额（按租户隔离）。

``PointTask.config`` 为 JSON，存储各检测方式所需的定制化配置，
例如 ``ticket_submit`` 可指定 ``category_id`` 仅特定分类工单计积分。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PointTask(Base, TimestampMixin):
    """积分任务：管理员配置的可获积分任务。"""

    __tablename__ = "point_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 检测方式标识，对应 PointTaskDetector.method_id
    detection_method: Mapped[str] = mapped_column(String(50), nullable=False)
    # 完成一次该任务获得的积分（可为负，表示扣分任务）
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 检测方式定制化配置（JSON），如 ticket_submit 可含 category_id
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # ── 关系 ──
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
    created_by: Mapped["User | None"] = relationship(  # noqa: F821
        foreign_keys=[created_by_id]
    )
    records: Mapped[list[PointRecord]] = relationship(
        back_populates="task", lazy="selectin"
    )


class PointRecord(Base):
    """积分明细流水：每次积分变动的不可变记录。"""

    __tablename__ = "point_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 变动数额（正为获得，负为消耗）
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    # 变动后余额快照
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    # 变动来源：task / admin / consume / refund
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("point_task.id", ondelete="SET NULL"), nullable=True
    )
    # 关联对象类型与 ID，如 ticket / account_opening / product
    ref_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ── 关系 ──
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821
    task: Mapped[PointTask | None] = relationship(
        back_populates="records", foreign_keys=[task_id]
    )
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )


class UserPoints(Base, TimestampMixin):
    """用户积分余额：按 (user, site_group) 维度隔离。"""

    __tablename__ = "user_points"
    __table_args__ = (
        UniqueConstraint("user_id", "site_group_id", name="uq_user_sitegroup_points"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("site_group.id", ondelete="SET NULL"), nullable=True, index=True
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── 关系 ──
    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821
    site_group: Mapped["SiteGroup | None"] = relationship(  # noqa: F821
        foreign_keys=[site_group_id]
    )
