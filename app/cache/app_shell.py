"""App Shell 边缘全量缓存。

策略（来自架构要求）：
- 页面骨架路由仅依据请求域名解析租户配置进行渲染，绝不依赖用户状态
- 通过按域名区分并配合 keyed-BLAKE2b 签名生成缓存键
- 实现 CDN 边缘节点全量高速缓存与防污染
- 缓存的 HTML 不含任何用户特定内容（无 Set-Cookie、无用户数据）
- 用户导航、统计等动态内容由 HTMX 在页面加载后独立请求获取
"""
from __future__ import annotations

from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.responses import HTMLResponse

from app.cache.keys import (
    app_shell_cache_key,
    compute_etag,
    edge_cache_headers,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.tenant.resolver import TenantContext

log = get_logger(__name__)


async def get_app_shell_cache(domain: str, path: str) -> str | None:
    """读取 App Shell 边缘缓存。返回 HTML 或 None。"""
    if not settings.redis_enabled:
        return None
    try:
        redis = await get_redis()
        key = app_shell_cache_key(domain, path)
        cached = await redis.get(key)
        return cached
    except Exception as e:  # noqa: BLE001
        log.warning("app_shell_cache_read_failed", error=str(e))
        return None


async def set_app_shell_cache(domain: str, path: str, html: str) -> None:
    """写入 App Shell 边缘缓存。"""
    if not settings.redis_enabled:
        return
    try:
        redis = await get_redis()
        key = app_shell_cache_key(domain, path)
        await redis.set(key, html, ex=settings.app_shell_cache_ttl)
    except Exception as e:  # noqa: BLE001
        log.warning("app_shell_cache_write_failed", error=str(e))


async def invalidate_app_shell(domain: str, path: str = "*") -> None:
    """失效 App Shell 缓存（租户配置变更时）。"""
    if not settings.redis_enabled:
        return
    try:
        redis = await get_redis()
        if path == "*":
            # 失效该域名所有 shell 缓存（用 scan）
            prefix = app_shell_cache_key(domain, "")
            async for key in redis.scan_iter(match=f"{prefix}*", count=100):
                await redis.delete(key)
        else:
            await redis.delete(app_shell_cache_key(domain, path))
    except Exception as e:  # noqa: BLE001
        log.warning("app_shell_cache_invalidate_failed", error=str(e))


async def render_app_shell(
    request: Request,
    tenant: TenantContext,
    path: str,
    render_fn: Callable[[], Awaitable[str]],
) -> HTMLResponse:
    """渲染 App Shell 页面（带边缘缓存）。

    - 先查缓存，命中直接返回（带 CDN 缓存头）
    - 未命中调用 render_fn 生成 HTML，写缓存后返回
    - 响应头标记为可缓存（public, max-age），不含 Set-Cookie
    """
    domain = tenant.hostname
    cached = await get_app_shell_cache(domain, path)
    if cached is not None:
        headers = edge_cache_headers(settings.app_shell_cache_ttl)
        headers["X-2C2A-Cache-Hit"] = "1"
        return HTMLResponse(content=cached, headers=headers)

    # 渲染
    html = await render_fn()
    await set_app_shell_cache(domain, path, html)

    headers = edge_cache_headers(settings.app_shell_cache_ttl)
    headers["X-2C2A-Cache-Hit"] = "0"
    etag = compute_etag(domain, path, str(len(html)))
    headers["ETag"] = etag
    return HTMLResponse(content=html, headers=headers)
