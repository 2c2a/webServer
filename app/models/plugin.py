"""插件模型。

PluginRecord 记录已安装的插件元数据。
PluginConfiguration 存储插件配置项，敏感值使用 value_cipher 加密存储。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class PluginRecord(Base, TimestampMixin):
    """插件记录：已安装插件的元数据。"""

    __tablename__ = "plugin_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plugin_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── 关系 ──
    configurations: Mapped[list[PluginConfiguration]] = relationship(
        back_populates="plugin", cascade="all, delete-orphan", lazy="selectin"
    )


class PluginConfiguration(Base, TimestampMixin):
    """插件配置项：键值对存储，敏感值加密。

    value_cipher 存储加密后的配置值，不存明文。
    """

    __tablename__ = "plugin_configuration"
    __table_args__ = (
        UniqueConstraint("plugin_id", "key", name="uq_plugin_configuration_plugin_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plugin_id: Mapped[int] = mapped_column(
        ForeignKey("plugin_record.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value_cipher: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── 关系 ──
    plugin: Mapped[PluginRecord] = relationship(back_populates="configurations")
