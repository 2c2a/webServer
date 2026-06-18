"""App Shell 页面骨架路由（可被 CDN 全量缓存）。

策略（来自架构要求）：
- 页面骨架路由仅依据请求域名解析租户配置进行渲染，绝不依赖用户状态
- 通过按域名区分并配合 keyed-BLAKE2b 签名生成缓存键
- 实现 CDN 边缘节点全量高速缓存与防污染
- 用户导航、统计等动态内容由 HTMX 在页面加载后独立请求获取
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.app_shell import render_app_shell
from app.core.db import get_db
from app.templates import render_template
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext, get_effective_config

router = APIRouter(tags=["shell"])


async def _shell_context(tenant: TenantContext, db: AsyncSession) -> dict:
    """构建 App Shell 渲染上下文（仅租户级配置，无用户状态）。"""
    cfg = await get_effective_config(db, tenant)
    return {
        "site_name": cfg.get("site_name") or "2c2a",
        "site_icon": cfg.get("site_icon"),
        "icp_number": cfg.get("icp_number"),
        "theme": "light",
        "enable_registration": cfg.get("enable_registration", False),
    }


@router.get("/")
async def dashboard_shell(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """仪表盘 App Shell（可缓存）。

    返回的 HTML 仅含租户配置 + 骨架占位，动态内容由 HTMX 加载。
    """

    async def render() -> str:
        ctx = await _shell_context(tenant, db)
        return await render_template("dashboard.html", **ctx)

    return await render_app_shell(request, tenant, "/", render)


@router.get("/login")
async def login_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """登录页 App Shell（可缓存）。"""

    async def render() -> str:
        ctx = await _shell_context(tenant, db)
        return await render_template("login.html", **ctx)

    return await render_app_shell(request, tenant, "/login", render)


@router.get("/register")
async def register_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """注册页 App Shell（可缓存）。"""

    async def render() -> str:
        ctx = await _shell_context(tenant, db)
        return await render_template("register.html", **ctx)

    return await render_app_shell(request, tenant, "/register", render)
