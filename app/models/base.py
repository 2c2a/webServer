"""SQLAlchemy 2.0 声明式基类与通用 Mixin。

采用 Mapped / mapped_column 新语法，全异步。
所有模型继承 TimestampMixin（created_at / updated_at）与软删除可选。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """声明式基类。"""

    def __repr__(self) -> str:  # pragma: no cover
        cls_name = self.__class__.__name__
        pk = getattr(self, "id", None)
        return f"<{cls_name} id={pk}>"


class TimestampMixin:
    """创建/更新时间戳。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPKMixin:
    """UUID 主键（适用于跨库分布式场景，可选）。"""

    id: Mapped[uuid.UUID] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )


class SiteGroupMixin:
    """站点隔离 Mixin：所有需要站点隔离的模型混入 site_group_id 字段。"""

    # 注意：site_group_id 在具体模型中用 ForeignKey 显式声明，
    # 此 Mixin 仅作标记，便于泛型查询过滤。
