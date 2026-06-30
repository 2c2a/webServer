"""RedisHuey 任务队列（替代 Celery）。

- 全异步任务执行（huey 的 async 支持）
- Redis 作为 broker
- 定时任务（crontab）替代 Celery Beat
- 任务状态通过 AsyncTask 模型追踪
"""
