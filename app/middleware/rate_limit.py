"""
限流中间件

基于 Redis 的请求限流，支持：
- IP 限流
- 用户限流
- 端点级别限流
- 返回 429 状态码和 Retry-After 头
"""
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

logger = logging.getLogger(__name__)

# 默认限流配置
DEFAULT_RATE_LIMITS = {
    "/api/auth/login": {"limit": 5, "period": 60},
    "/api/auth/register": {"limit": 3, "period": 3600},
    "/api/auth/forgot-password": {"limit": 3, "period": 300},
    "/api/auth/send-code": {"limit": 5, "period": 300},
}

# 全局限流
GLOBAL_RATE_LIMIT = {"limit": 100, "period": 60}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    限流中间件

    使用 Redis 滑动窗口计数器实现请求限流。
    支持按 IP 和用户 ID 限流。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 跳过非 API 路径
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # 跳过健康检查
        if request.url.path in ("/health", "/api/health"):
            return await call_next(request)

        settings = get_settings()

        # 检查端点级别限流
        endpoint_limit = self._get_endpoint_limit(request.url.path)
        if endpoint_limit:
            identifier = self._get_identifier(request)
            key = f"rate_limit:endpoint:{request.url.path}:{identifier}"
            allowed = await self._check_rate_limit(key, endpoint_limit["limit"], endpoint_limit["period"])
            if not allowed:
                return self._rate_limit_response(endpoint_limit["period"])

        # 检查全局限流
        identifier = self._get_identifier(request)
        global_key = f"rate_limit:global:{identifier}"
        global_limit = settings.api_rate_limit or GLOBAL_RATE_LIMIT["limit"]
        allowed = await self._check_rate_limit(global_key, global_limit, GLOBAL_RATE_LIMIT["period"])
        if not allowed:
            return self._rate_limit_response(GLOBAL_RATE_LIMIT["period"])

        return await call_next(request)

    @staticmethod
    def _get_identifier(request: Request) -> str:
        """获取限流标识符（优先使用用户 ID，其次使用 IP）"""
        # 尝试从 request.state 获取用户信息
        user = getattr(request.state, "user", None)
        if user and hasattr(user, "id"):
            return f"user:{user.id}"

        # 回退到 IP
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0].strip()
        elif request.client:
            ip = request.client.host
        else:
            ip = "unknown"

        return f"ip:{ip}"

    @staticmethod
    def _get_endpoint_limit(path: str) -> Optional[dict]:
        """获取端点级别的限流配置"""
        # 精确匹配
        if path in DEFAULT_RATE_LIMITS:
            return DEFAULT_RATE_LIMITS[path]

        # 前缀匹配
        for endpoint, config in DEFAULT_RATE_LIMITS.items():
            if path.startswith(endpoint):
                return config

        return None

    @staticmethod
    async def _check_rate_limit(key: str, limit: int, period: int) -> bool:
        """
        检查是否超过限流

        使用 Redis INCR + EXPIRE 实现固定窗口计数器

        Returns:
            True: 允许请求, False: 超过限流
        """
        try:
            from app.services.redis_helper import get_redis
            redis = await get_redis()

            current = await redis.get(key)
            if current is not None:
                current_count = int(current)
                if current_count >= limit:
                    logger.warning("限流触发: key=%s, count=%d, limit=%d", key, current_count, limit)
                    return False

            # 递增计数
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, period)
            await pipe.execute()

            return True
        except Exception:
            # Redis 不可用时放行请求
            logger.exception("限流检查失败，放行请求")
            return True

    @staticmethod
    def _rate_limit_response(retry_after: int) -> JSONResponse:
        """生成限流响应"""
        return JSONResponse(
            status_code=429,
            content={
                "detail": "请求过于频繁，请稍后再试",
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


# ========== 限流辅助函数（供路由装饰器使用）==========

async def check_rate_limit(
    key: str,
    limit: int,
    period: int = 60,
) -> bool:
    """
    检查是否超过限流（供路由使用）

    Args:
        key: 限流键
        limit: 限制次数
        period: 时间窗口（秒）

    Returns:
        True: 允许, False: 超限
    """
    return await RateLimitMiddleware._check_rate_limit(key, limit, period)


async def check_ip_rate_limit(
    ip: str,
    action: str,
    limit: int = 10,
    period: int = 60,
) -> bool:
    """
    基于 IP 的限流检查

    Args:
        ip: 客户端 IP
        action: 操作类型
        limit: 限制次数
        period: 时间窗口（秒）

    Returns:
        True: 允许, False: 超限
    """
    key = f"rate_limit:ip:{action}:{ip}"
    return await check_rate_limit(key, limit, period)


async def check_user_rate_limit(
    user_id: str,
    action: str,
    limit: int = 10,
    period: int = 60,
) -> bool:
    """
    基于用户 ID 的限流检查

    Args:
        user_id: 用户 ID
        action: 操作类型
        limit: 限制次数
        period: 时间窗口（秒）

    Returns:
        True: 允许, False: 超限
    """
    key = f"rate_limit:user:{action}:{user_id}"
    return await check_rate_limit(key, limit, period)
