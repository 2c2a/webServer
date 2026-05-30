"""
2c2a配置模块
"""
from .celery import app as celery_app  # noqa: E402,F401

__all__ = ('celery_app',)
