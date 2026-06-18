"""Huey 任务队列实例与配置。"""
from __future__ import annotations

from huey import RedisHuey, crontab

from app.core.config import settings

# Huey 实例：Redis broker
# 调试模式且无 Redis 时使用 immediate 模式（同步执行，便于开发）
_immediate = settings.debug and not settings.redis_enabled

huey = RedisHuey(
    "2c2a",
    url=settings.redis_url,
    immediate=_immediate,
)

# 定时任务调度（替代 Celery Beat）
# 格式：crontab(minute, hour, day, month, day_of_week)
# 用法：@huey.periodic_task(crontab(hour=0, minute=0))
__all__ = ["huey", "crontab"]
