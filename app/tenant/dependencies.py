"""租户 FastAPI 依赖注入与中间件。

- TenantMiddleware：每个请求解析租户并挂到 request.state.tenant
- get_tenant：依赖注入，返回 TenantContext
- get_db_with_tenant：组合数据库会话与租户上下文
- reject_demo：演示站点禁止写操作（如站点组管理）的守卫依赖
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import AppError, TenantError
from app.tenant.resolver import TenantContext, resolve_tenant_by_hostname


async def get_tenant(request: Request) -> TenantContext:
    """从 request.state 获取租户上下文（由中间件注入）。"""
    tenant: TenantContext | None = getattr(request.state, "tenant", None)
    if tenant is None:
        raise TenantError("租户上下文未初始化")
    return tenant


async def reject_demo(request: Request) -> None:
    """演示站点禁止敏感写操作的守卫依赖。

    当全局 ``settings.demo`` 开启且当前请求域名解析到的站点
    ``SiteGroup.is_demo=True`` 时，拒绝执行。
    用于站点组创建/更新等不允许在演示环境操作的路由。
    """
    tenant: TenantContext | None = getattr(request.state, "tenant", None)
    if tenant is not None and tenant.is_demo:
        raise AppError(
            "演示站点不允许操作站点组", code="demo_forbidden", status=403
        )


def get_client_ip(request: Request) -> str:
    """获取真实客户端 IP（考虑可信代理）。"""
    if settings.use_x_forwarded_for:
        xf = request.headers.get("x-forwarded-for")
        if xf:
            # 取第一个 IP
            return xf.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


async def get_db_tenant(
    request: Request,
) -> AsyncIterator[tuple[AsyncSession, TenantContext]]:
    """组合依赖：数据库会话 + 租户上下文。"""
    tenant = await get_tenant(request)
    async for db in get_db():
        yield db, tenant


# 便捷别名
DBTenant = Depends(get_db_tenant)
TenantDep = Depends(get_tenant)
