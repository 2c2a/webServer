"""Redis 异步客户端。

提供全局 Redis 连接池，用于：
- 缓存（租户配置、App Shell 元数据）
- 速率限制
- RedisHuey 任务队列 broker
"""
from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import settings

_redis: Redis | None = None


async def get_redis() -> Redis:
    """获取全局 Redis 客户端（单例）。"""
    global _redis
    if _redis is None:
        _redis = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=50,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
