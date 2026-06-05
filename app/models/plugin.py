"""
插件模型

包含 PluginRecord
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PluginRecord(Base):
    """插件记录模型"""
    __tablename__ = "plugin_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plugin_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    configurations: Mapped[list["PluginConfiguration"]] = relationship(
        "PluginConfiguration", back_populates="plugin"
    )

    def __repr__(self) -> str:
        return f"<PluginRecord {self.name} v{self.version}>"


class PluginConfiguration(Base):
    """插件配置模型"""
    __tablename__ = "plugin_configuration"
    __table_args__ = (
        UniqueConstraint("plugin_id", "key", name="unique_plugin_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plugin_id: Mapped[str] = mapped_column(String(36), ForeignKey("plugin_record.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # relationships
    plugin: Mapped["PluginRecord"] = relationship("PluginRecord", back_populates="configurations")

    def __repr__(self) -> str:
        return f"<PluginConfiguration {self.plugin_id}:{self.key}>"
