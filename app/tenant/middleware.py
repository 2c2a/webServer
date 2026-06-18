"""租户中间件：按请求域名解析租户并注入 request.state.tenant。

此中间件在所有路由前执行，确保每个请求都带有租户上下文。
解析结果缓存到 Redis，避免每次查库。
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.tenant.resolver import TenantContext, resolve_tenant_by_hostname

log = get_logger(__name__)


class TenantMiddleware(BaseHTTPMiddleware):
    """按域名解析租户的中间件。"""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 静态文件与健康检查跳过租户解析
        path = request.url.path
        if path.startswith("/static") or path in ("/health", "/favicon.ico"):
            request.state.tenant = TenantContext(
                hostname=request.url.hostname or "localhost", is_default=True
            )
            return await call_next(request)

        hostname = request.url.hostname or "localhost"

        # 用独立短生命周期会话解析租户（不污染路由层会话）
        async with AsyncSessionLocal() as db:
            try:
                tenant = await resolve_tenant_by_hostname(db, hostname)
            except Exception as e:  # noqa: BLE001
                log.warning("tenant_resolve_failed", hostname=hostname, error=str(e))
                tenant = TenantContext(hostname=hostname, is_default=True)

        request.state.tenant = tenant
        response = await call_next(request)
        # 在响应头标注租户信息（便于调试，不含敏感数据）
        response.headers["X-Tenant"] = tenant.hostname
        if not tenant.is_default:
            response.headers["X-Tenant-Group"] = str(tenant.site_group_id)
        return response
