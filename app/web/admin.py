"""管理后台页面路由（.design 体系，Vercel 主题）。

页面源自 2c2a-admin-console.design，继承 admin_shell.html 布局。
权限控制由依赖注入完成：未登录/无权限用户直接收到 401/403。

管理后台不走 App Shell 边缘缓存（页面含当前用户信息，不可跨用户共享）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import HTMLResponse

from app.auth.dependencies import CurrentUser, require_staff, require_superuser
from app.core.db import get_db
from app.templates import render_template
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext, get_effective_config

router = APIRouter(tags=["admin"])


async def _admin_context(
    tenant: TenantContext, db: AsyncSession, user: CurrentUser | None = None
) -> dict:
    """构建管理后台渲染上下文（租户级配置 + 页面变量 + 当前用户）。"""
    cfg = await get_effective_config(db, tenant)
    return {
        "site_name": cfg.get("site_name") or "2c2a",
        "site_icon": cfg.get("site_icon"),
        "icp_number": cfg.get("icp_number"),
        "theme": "light",
        "current_user": user,
    }


async def _render(
    tenant: TenantContext,
    db: AsyncSession,
    template: str,
    user: CurrentUser | None = None,
    **extra: object,
) -> HTMLResponse:
    """直接渲染管理后台页面（不走 App Shell 缓存）。

    extra 用于把路径参数（user_id/host_id 等）传入模板，供 HTMX 触发
    ``/fragments/admin/xxx?...=`` 时使用。
    """
    ctx = await _admin_context(tenant, db, user)
    ctx.update(extra)
    html = await render_template(template, **ctx)
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# 列表页
# ---------------------------------------------------------------------------


@router.get("/admin/")
async def admin_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """后台概览。"""
    return await _render(tenant, db, "admin/overview.html", user=user)


@router.get("/admin/users")
async def admin_users(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """用户管理列表。"""
    return await _render(tenant, db, "admin/users.html", user=user)


@router.get("/admin/hosts")
async def admin_hosts(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """主机管理列表。"""
    return await _render(tenant, db, "admin/hosts.html", user=user)


@router.get("/admin/hosts/groups")
async def admin_host_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """主机组管理。"""
    return await _render(tenant, db, "admin/host_groups.html", user=user)


@router.get("/admin/tickets")
async def admin_tickets(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """工单管理列表。"""
    return await _render(tenant, db, "admin/tickets.html", user=user)


@router.get("/admin/openings")
async def admin_openings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """开户申请列表。"""
    return await _render(tenant, db, "admin/openings.html", user=user)


@router.get("/admin/products")
async def admin_products(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """产品管理列表。"""
    return await _render(tenant, db, "admin/products.html", user=user)


@router.get("/admin/points")
async def admin_points(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """积分管理列表。"""
    return await _render(tenant, db, "admin/points.html", user=user)


@router.get("/admin/audit")
async def admin_audit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """审计日志。"""
    return await _render(tenant, db, "admin/audit.html", user=user)


@router.get("/admin/announcements")
async def admin_announcements(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """公告管理列表。"""
    return await _render(tenant, db, "admin/announcements.html", user=user)


@router.get("/admin/sitegroups")
async def admin_sitegroups(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_superuser),
):
    """站点组管理（仅超管）。"""
    return await _render(tenant, db, "admin/sitegroups.html", user=user)


@router.get("/admin/sitegroups/new")
async def admin_sitegroup_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_superuser),
):
    """新建站点组表单（仅超管）。

    注意：此路由必须注册在 /admin/sitegroups/{site_group_id} 之前，否则
    'new' 会被当作 site_group_id 解析为 int 失败（FastAPI 按注册顺序匹配）。
    """
    return await _render(tenant, db, "admin/sitegroup_form.html", user=user)


@router.get("/admin/settings")
async def admin_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """系统配置。"""
    return await _render(tenant, db, "admin/settings.html", user=user)


# ---------------------------------------------------------------------------
# 详情页
# ---------------------------------------------------------------------------


@router.get("/admin/users/new")
async def admin_user_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """新建用户表单。

    注意：此路由必须注册在 /admin/users/{user_id} 之前，否则 'new' 会被
    当作 user_id 解析为 int 失败（FastAPI 按注册顺序匹配）。
    """
    return await _render(tenant, db, "admin/user_form.html", user=user)


@router.get("/admin/users/{user_id}")
async def admin_user_detail(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """用户详情。"""
    return await _render(
        tenant, db, "admin/user_detail.html", user=user, user_id=user_id
    )


@router.get("/admin/tickets/{ticket_id}")
async def admin_ticket_detail(
    ticket_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """工单详情。"""
    return await _render(
        tenant, db, "admin/ticket_detail.html", user=user, ticket_id=ticket_id
    )


@router.get("/admin/openings/{opening_id}")
async def admin_opening_review(
    opening_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """开户申请审核详情。"""
    return await _render(
        tenant, db, "admin/opening_review.html", user=user, opening_id=opening_id
    )


# ---------------------------------------------------------------------------
# 表单页
# ---------------------------------------------------------------------------


@router.get("/admin/users/{user_id}/edit")
async def admin_user_edit_form(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """编辑用户表单。"""
    return await _render(
        tenant, db, "admin/user_form.html", user=user, user_id=user_id
    )


@router.get("/admin/hosts/new")
async def admin_host_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """新建主机表单。"""
    return await _render(tenant, db, "admin/host_form.html", user=user)


@router.get("/admin/hosts/{host_id}/edit")
async def admin_host_edit_form(
    host_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """编辑主机表单。"""
    return await _render(
        tenant, db, "admin/host_form.html", user=user, host_id=host_id
    )


@router.get("/admin/products/new")
async def admin_product_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """新建产品表单。"""
    return await _render(tenant, db, "admin/product_form.html", user=user)


@router.get("/admin/products/{product_id}/edit")
async def admin_product_edit_form(
    product_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """编辑产品表单。"""
    return await _render(
        tenant, db, "admin/product_form.html", user=user, product_id=product_id
    )


@router.get("/admin/points/tasks/new")
async def admin_points_task_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """新建积分任务表单。"""
    return await _render(tenant, db, "admin/points_task_form.html", user=user)


@router.get("/admin/points/tasks/{task_id}/edit")
async def admin_points_task_edit_form(
    task_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """编辑积分任务表单。"""
    return await _render(
        tenant, db, "admin/points_task_form.html", user=user, task_id=task_id
    )


@router.get("/admin/announcements/new")
async def admin_announcement_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """新建公告表单。

    注意：此路由必须注册在 /admin/announcements/{announcement_id}/edit 之前，否则
    'new' 会被当作 announcement_id 解析为 int 失败（FastAPI 按注册顺序匹配）。
    """
    return await _render(tenant, db, "admin/announcement_form.html", user=user)


@router.get("/admin/announcements/{announcement_id}/edit")
async def admin_announcement_edit_form(
    announcement_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """编辑公告表单。"""
    return await _render(
        tenant, db, "admin/announcement_form.html", user=user, announcement_id=announcement_id
    )
