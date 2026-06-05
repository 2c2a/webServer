"""
维护模式中间件

检查系统配置中的维护状态，在维护模式下：
1. 阻止本地访问（当 local_access_locked 启用时）
2. 返回维护页面（当 REPAIRING 环境变量启用时）
"""
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

LOCAL_IPS = frozenset({
    '127.0.0.1',
    '::1',
    '0.0.0.0',
    '0000:0000:0000:0000:0000:0000:0000:0001',
})

LOCAL_HOSTNAMES = frozenset({
    'localhost',
})

# 维护模式下排除的路径
MAINTENANCE_EXCLUDED_PATHS = (
    '/static/',
    '/media/',
    '/docs',
    '/openapi.json',
    '/health',
)

# 本地锁定模式下排除的路径
LOCAL_LOCK_EXCLUDED_PATHS = (
    '/static/',
    '/media/',
)


class MaintenanceMiddleware(BaseHTTPMiddleware):
    """
    维护模式中间件

    功能：
    1. 当 REPAIRING 环境变量为 1 时，返回 503 维护页面
    2. 当 SystemConfig.local_access_locked 为 True 时，阻止本地访问
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. 检查本地访问锁定
        client_ip = self._get_client_ip(request)
        if client_ip and self._is_local_ip(client_ip):
            if await self._is_local_access_locked():
                if not any(request.url.path.startswith(p) for p in LOCAL_LOCK_EXCLUDED_PATHS):
                    logger.warning("本地访问已禁止，拒绝来自 %s 的请求: %s", client_ip, request.url.path)
                    return Response(status_code=403, content="本地访问已被禁止")

        # 2. 检查维护模式
        repairing = os.environ.get('REPAIRING', '0')
        is_repairing = repairing.lower() in ('1', 'true', 'on', 'yes', 'enabled')

        if is_repairing:
            if not any(request.url.path.startswith(p) for p in MAINTENANCE_EXCLUDED_PATHS):
                # AJAX 请求返回 JSON
                if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return JSONResponse(
                        status_code=503,
                        content={
                            "error": "系统正在维护中，请稍后再试",
                            "maintenance": True,
                        },
                    )
                # 普通请求返回 503
                return Response(
                    status_code=503,
                    content="""
<!DOCTYPE html>
<html>
<head><title>系统维护中</title></head>
<body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;">
<div style="text-align:center;">
<h1>🔧 系统维护中</h1>
<p>系统正在维护中，请稍后再试。</p>
</div>
</body>
</html>
""",
                    media_type="text/html",
                )

        return await call_next(request)

    @staticmethod
    def _get_client_ip(request: Request) -> str | None:
        """获取客户端 IP"""
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        if request.client:
            return request.client.host
        return None

    @staticmethod
    def _is_local_ip(ip: str) -> bool:
        """判断是否为本地 IP"""
        return ip in LOCAL_IPS or ip.lower() in LOCAL_HOSTNAMES

    @staticmethod
    async def _is_local_access_locked() -> bool:
        """检查本地访问是否被锁定（查询数据库）"""
        try:
            from sqlalchemy import select

            from app.database import async_session_factory
            from app.models.dashboard import SystemConfig

            async with async_session_factory() as session:
                result = await session.execute(
                    select(SystemConfig).where(SystemConfig.id == 1)
                )
                config = result.scalar_one_or_none()
                if config:
                    return config.local_access_locked
        except Exception:
            logger.exception("检查本地访问锁定状态异常，默认拒绝")
            return True
        return False
