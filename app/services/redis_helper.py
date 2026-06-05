"""
Redis 异步连接池

提供 async Redis 客户端单例，基于连接池
"""
import logging

from redis.asyncio import ConnectionPool, Redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


async def _get_pool() -> ConnectionPool:
    """获取或创建异步连接池（单例）"""
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool.from_url(
            settings.redis_url,
            max_connections=20,
            decode_responses=True,
        )
        logger.info("Redis 异步连接池已创建: %s", settings.redis_url)
    return _pool


async def get_redis() -> Redis:
    """获取异步 Redis 客户端"""
    pool = await _get_pool()
    return Redis(connection_pool=pool)


async def close_redis() -> None:
    """关闭连接池（应用关闭时调用）"""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
        logger.info("Redis 异步连接池已关闭")
