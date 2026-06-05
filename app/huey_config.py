"""
Huey 任务队列配置

使用 Redis 作为 broker，支持定时任务
Huey 轻量高效，适合本项目规模
"""

from huey import RedisHuey, crontab

from app.config import get_settings

settings = get_settings()

huey = RedisHuey(
    "2c2a",
    url=settings.huey_redis_url,
    immediate=settings.huey_immediate,
)
