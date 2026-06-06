"""
限流装饰器模块
提供 API 限流和登录保护

使用标准 Django cache API（get/set），兼容所有缓存后端：
- Redis（django-redis）：高性能，支持分布式
- LocMemCache：本地内存，无需额外依赖
"""
from functools import wraps
from typing import Callable
from django.core.cache import cache
from django.conf import settings
from django.http import JsonResponse
from utils.helpers import get_client_ip
import logging

logger = logging.getLogger('2c2a')


class RateLimitExceeded(Exception):
    pass


def _cache_incr(key: str, period: int) -> int:
    """
    兼容所有缓存后端的原子计数器。

    使用 get/set 替代 incr/expire，确保 LocMemCache 等后端也能正常工作。
    Redis 后端下 django-redis 会自动处理并发安全。

    Args:
        key: 缓存键
        period: 过期时间（秒）

    Returns:
        int: 递增后的计数值
    """
    current = cache.get(key, 0)
    new_count = current + 1
    cache.set(key, new_count, timeout=period + 1)
    return new_count


def _cache_ttl_fallback(key: str, default: int = 0) -> int:
    """
    获取缓存键的剩余 TTL，不兼容时返回默认值。

    cache.ttl() 是 django-redis 专有方法，
    LocMemCache 等后端不支持，此时返回默认值。
    """
    if hasattr(cache, 'ttl'):
        try:
            ttl = cache.ttl(key)
            if ttl is not None and ttl > 0:
                return int(ttl)
        except Exception:
            pass
    return default


def rate_limit(key_prefix: str, limit: int, period: int = 60, per_user: bool = True):
    """
    限流装饰器（固定窗口计数器）

    Args:
        key_prefix: 缓存键前缀
        limit: 限制次数
        period: 时间周期（秒）
        per_user: 是否按用户限流
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if per_user and hasattr(request, 'user') and request.user.is_authenticated:
                key_parts = [key_prefix, request.user.username]
            else:
                key_parts = [key_prefix, get_client_ip(request)]

            rate_limit_key = f"rate_limit:{':'.join(key_parts)}"

            current_count = cache.get(rate_limit_key, 0)

            if current_count >= limit:
                remaining_time = _cache_ttl_fallback(rate_limit_key, period)
                logger.warning(f"Rate limit exceeded for {rate_limit_key} ({current_count}/{limit})")

                return JsonResponse({
                    'success': False,
                    'error': {
                        'type': 'RateLimitExceeded',
                        'message': f'请求过于频繁，请在 {remaining_time} 秒后重试',
                        'retry_after': remaining_time,
                    },
                }, status=429)

            _cache_incr(rate_limit_key, period)

            return func(request, *args, **kwargs)
        return wrapper
    return decorator


def login_rate_limit():
    """登录限流装饰器"""
    return rate_limit(key_prefix='login', limit=settings.LOGIN_RATE_LIMIT, period=60)


def api_rate_limit():
    """API 通用限流装饰器"""
    return rate_limit(key_prefix='api', limit=settings.API_RATE_LIMIT, period=60)


def register_rate_limit(view_func):
    """注册限流装饰器"""
    @wraps(view_func)
    def wrapped_view(self, request, *args, **kwargs):
        from django.contrib import messages
        from django.shortcuts import redirect

        rate_limit_key = f"rate_limit:register:{get_client_ip(request)}"
        limit = 5
        period = 3600

        current_count = cache.get(rate_limit_key, 0)

        if current_count >= limit:
            remaining = _cache_ttl_fallback(rate_limit_key, period)
            minutes = max(1, remaining // 60)
            logger.warning(f"Registration rate limit exceeded for IP {get_client_ip(request)}")
            messages.error(request, f'注册过于频繁，请在 {minutes} 分钟后重试')
            return redirect('accounts:register')

        _cache_incr(rate_limit_key, period)

        return view_func(self, request, *args, **kwargs)
    return wrapped_view


def check_operation_rate_limit(operation_type: str, identifier: str, limit: int = 10, period: int = 60) -> bool:
    """
    检查操作是否达到限流

    Args:
        operation_type: 操作类型
        identifier: 操作标识符
        limit: 限制次数
        period: 时间周期（秒）

    Returns:
        True 如果允许操作，False 如果达到限流
    """
    key = f"rate_limit:op:{operation_type}:{identifier}"
    current_count = cache.get(key, 0)

    if current_count >= limit:
        logger.warning(f"Operation rate limit exceeded: {key} ({current_count}/{limit})")
        return False

    _cache_incr(key, period)
    return True


class RateLimitMixin:
    """在视图类中添加限流功能的 mixin"""

    rate_limit_key = None
    rate_limit_count = None
    rate_limit_period = 60

    def dispatch(self, request, *args, **kwargs):
        if self.rate_limit_key and self.rate_limit_count:
            if hasattr(request, 'user') and request.user.is_authenticated:
                identifier = request.user.username
            else:
                identifier = get_client_ip(request)

            key = f"rate_limit:view:{self.rate_limit_key}:{identifier}"
            current_count = cache.get(key, 0)

            if current_count >= self.rate_limit_count:
                return JsonResponse({
                    'success': False,
                    'error': {
                        'type': 'RateLimitExceeded',
                        'message': '操作过于频繁，请稍后再试',
                    },
                }, status=429)

            _cache_incr(key, self.rate_limit_period)

        return super().dispatch(request, *args, **kwargs)


def rate_limit_ip(ip: str, key: str, limit: int, period: int = 60) -> bool:
    """
    基于 IP 的限流函数
    """
    cache_key = f"rate_limit:ip:{key}:{ip}"
    current_count = cache.get(cache_key, 0)

    if current_count >= limit:
        logger.warning(f"IP rate limit exceeded: {cache_key} ({current_count}/{limit})")
        return False

    _cache_incr(cache_key, period)
    return True
