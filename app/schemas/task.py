"""
异步任务 Pydantic 模式

包含异步任务、任务进度等模式
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ─── 任务进度模式 ───────────────────────────────────────────


class TaskProgressResponse(BaseModel):
    """任务进度响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    progress: int
    message: Optional[str] = None
    timestamp: Optional[datetime] = None


# ─── 异步任务模式 ───────────────────────────────────────────


class AsyncTaskResponse(BaseModel):
    """异步任务响应"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    name: str
    status: str = "pending"
    progress: int = 0
    result: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
