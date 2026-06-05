"""
异步任务模型

包含 AsyncTask, TaskProgress
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AsyncTask(Base):
    """异步任务状态跟踪模型"""
    __tablename__ = "async_task"
    __table_args__ = (
        Index("ix_asynctask_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_by_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_object_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # relationships
    created_by: Mapped["User | None"] = relationship("User", foreign_keys=[created_by_id])
    progress_updates: Mapped[list["TaskProgress"]] = relationship("TaskProgress", back_populates="task")

    def __repr__(self) -> str:
        return f"<AsyncTask {self.name} [{self.status}]>"


class TaskProgress(Base):
    """任务进度详情模型"""
    __tablename__ = "task_progress"
    __table_args__ = (
        Index("ix_taskprogress_task_timestamp", "task_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("async_task.id"), nullable=False)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    task: Mapped["AsyncTask"] = relationship("AsyncTask", back_populates="progress_updates")

    def __repr__(self) -> str:
        return f"<TaskProgress {self.task_id} {self.progress}%>"
