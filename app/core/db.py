"""SQLAlchemy 2.0 异步引擎与会话工厂。

采用 async_sessionmaker + AsyncSession，所有数据库操作均为异步非阻塞。
会话通过 FastAPI 依赖注入 `get_db` 提供给路由层。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# 异步引擎：连接池仅在非 SQLite 时启用
_engine_kwargs: dict = {"echo": settings.db_echo}
if settings.db_engine != "sqlite":
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

engine = create_async_engine(settings.database_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：提供异步数据库会话，请求结束自动关闭。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """应用关闭时释放连接池。"""
    await engine.dispose()
