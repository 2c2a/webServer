"""
站点组解析中间件

根据请求的 Host 头解析对应的站点组，
将结果设置到 request.state.site_group。
"""
import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SiteGroupMiddleware(BaseHTTPMiddleware):
    """
    站点组中间件

    从请求的 Host 头解析站点组，设置到 request.state.site_group。
    使用 Redis 缓存解析结果，减少数据库查询。
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        site_group = await self._resolve_site_group(request)
        request.state.site_group = site_group
        return await call_next(request)

    async def _resolve_site_group(self, request: Request) -> Optional[dict]:
        """
        解析请求对应的站点组

        Returns:
            站点组信息字典，或 None
        """
        try:
            host_header = request.headers.get("host", "")
            hostname = host_header.split(":")[0] if host_header else ""
        except Exception:
            return None

        if not hostname:
            return None

        # 先查 Redis 缓存
        cache_key = f"site_group:hostname:{hostname}"
        try:
            from app.services.redis_helper import get_redis
            redis = await get_redis()
            cached_id = await redis.get(cache_key)

            if cached_id is not None:
                if cached_id == "0":
                    return None
                # 从数据库获取站点组
                site_group = await self._get_site_group_by_id(cached_id)
                if site_group:
                    return site_group
                # 缓存过期，删除
                await redis.delete(cache_key)
                return None
        except Exception:
            logger.debug("Redis 缓存查询失败，回退到数据库查询")

        # 从数据库查询
        site_group = await self._get_site_group_by_hostname(hostname)

        # 写入缓存
        try:
            from app.services.redis_helper import get_redis
            redis = await get_redis()
            if site_group:
                await redis.setex(cache_key, 300, site_group["id"])
            else:
                await redis.setex(cache_key, 300, "0")
        except Exception:
            logger.debug("Redis 缓存写入失败")

        return site_group

    @staticmethod
    async def _get_site_group_by_id(site_group_id: str) -> Optional[dict]:
        """通过 ID 获取站点组信息"""
        try:
            from sqlalchemy import select

            from app.database import async_session_factory
            from app.models.dashboard import SiteGroup

            async with async_session_factory() as session:
                result = await session.execute(
                    select(SiteGroup).where(
                        SiteGroup.id == site_group_id,
                        SiteGroup.is_active == True,  # noqa: E712
                    )
                )
                sg = result.scalar_one_or_none()
                if sg:
                    return {
                        "id": sg.id,
                        "name": sg.name,
                        "slug": sg.slug,
                        "site_name": sg.site_name,
                        "site_icon": sg.site_icon,
                    }
        except Exception:
            logger.exception("查询站点组失败")
        return None

    @staticmethod
    async def _get_site_group_by_hostname(hostname: str) -> Optional[dict]:
        """通过主机名获取站点组信息"""
        try:
            from sqlalchemy import select

            from app.database import async_session_factory
            from app.models.dashboard import SiteGroup, SiteGroupHostname

            async with async_session_factory() as session:
                result = await session.execute(
                    select(SiteGroupHostname)
                    .where(SiteGroupHostname.hostname == hostname)
                )
                mapping = result.scalar_one_or_none()
                if not mapping:
                    return None

                # 获取站点组
                sg_result = await session.execute(
                    select(SiteGroup).where(
                        SiteGroup.id == mapping.site_group_id,
                        SiteGroup.is_active == True,  # noqa: E712
                    )
                )
                sg = sg_result.scalar_one_or_none()
                if sg:
                    return {
                        "id": sg.id,
                        "name": sg.name,
                        "slug": sg.slug,
                        "site_name": sg.site_name,
                        "site_icon": sg.site_icon,
                    }
        except Exception:
            logger.exception("通过主机名查询站点组失败")
        return None
