"""HTMX 动态片段路由（不可缓存、基于用户状态与租户依赖）。

策略（来自架构要求）：
- 用户导航、统计等动态内容由 HTMX 在页面加载后发起独立请求
- 服务端基于 Ed25519 验签和租户依赖实时返回不可缓存的 HTML 片段
- 片段响应标记 no-store，确保数据安全隔离
- 支持 HTMX OOB（Out of Band）swap
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user_optional
from app.cache.fragments import fragment_response, oob_fragment
from app.core.db import get_db
from app.models.operations import AccountOpeningRequest, CloudComputerUser, Product, ProductGroup
from app.models.host import Host
from app.models.ticket import Ticket
from app.templates import render_template
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/fragments", tags=["fragments"])


@router.get("/nav")
async def nav_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """导航片段（基于用户状态，不可缓存）。"""
    cfg = {}
    try:
        from app.tenant.resolver import get_effective_config

        cfg = await get_effective_config(db, tenant)
    except Exception:  # noqa: BLE001
        pass

    html = await render_template(
        "nav.html",
        user=user,
        enable_registration=cfg.get("enable_registration", False),
    )
    return fragment_response(html, request=request)


@router.get("/stats")
async def stats_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """统计片段（基于用户权限，不可缓存）。

    普通用户看自己的统计，管理员看全局/租户统计。
    """
    if user is None:
        return fragment_response("<div></div>", request=request)

    # 站点隔离过滤
    sg_filter = []
    if tenant.site_group_id and not user.is_superuser:
        sg_filter = [Host.site_group_id == tenant.site_group_id]

    hosts_count = 0
    cloud_users_count = 0
    pending_tickets = 0
    pending_requests = 0

    try:
        if user.is_staff or user.is_superuser:
            hosts_result = await db.execute(
                select(func.count(Host.id)).where(*sg_filter)
            )
            hosts_count = hosts_result.scalar() or 0
        else:
            hosts_count = 0

        # 云电脑用户数
        cc_filter = []
        if not (user.is_staff or user.is_superuser):
            cc_filter = [CloudComputerUser.owner_id == user.id]
        cc_result = await db.execute(
            select(func.count(CloudComputerUser.id)).where(*cc_filter)
        )
        cloud_users_count = cc_result.scalar() or 0

        # 待处理工单
        ticket_filter = [Ticket.status.in_(["open", "pending", "processing"])]
        if not (user.is_staff or user.is_superuser):
            ticket_filter.append(Ticket.creator_id == user.id)
        ticket_result = await db.execute(
            select(func.count(Ticket.id)).where(*ticket_filter)
        )
        pending_tickets = ticket_result.scalar() or 0

        # 待处理开户申请
        req_filter = [AccountOpeningRequest.status == "pending"]
        if not (user.is_staff or user.is_superuser):
            req_filter.append(AccountOpeningRequest.applicant_id == user.id)
        req_result = await db.execute(
            select(func.count(AccountOpeningRequest.id)).where(*req_filter)
        )
        pending_requests = req_result.scalar() or 0
    except Exception:  # noqa: BLE001
        pass

    html = await render_template(
        "stats.html",
        stats={
            "hosts_count": hosts_count,
            "cloud_users_count": cloud_users_count,
            "pending_tickets": pending_tickets,
            "pending_requests": pending_requests,
        },
    )
    return fragment_response(html, request=request)


@router.get("/product-groups")
async def product_groups_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """产品组片段（基于租户隔离与可见性，不可缓存）。"""
    # 站点隔离 + 仅公开可见
    filters = [ProductGroup.is_active == True, ProductGroup.visibility == "public"]  # noqa: E712
    if tenant.site_group_id:
        filters.append(
            (ProductGroup.site_group_id == tenant.site_group_id)
            | (ProductGroup.site_group_id.is_(None))
        )

    result = await db.execute(
        select(ProductGroup)
        .where(*filters)
        .order_by(ProductGroup.display_order)
    )
    groups = result.scalars().all()

    # 加载每组的产品
    product_groups = []
    for pg in groups:
        prod_result = await db.execute(
            select(Product)
            .where(
                Product.product_group_id == pg.id,
                Product.is_available == True,  # noqa: E712
            )
            .order_by(Product.id)
        )
        products = prod_result.scalars().all()
        product_groups.append({"name": pg.name, "description": pg.description, "products": products})

    html = await render_template("product_groups.html", product_groups=product_groups)
    return fragment_response(html, request=request)


@router.get("/my-cloud-computers")
async def my_cloud_computers_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """我的云电脑片段（基于用户，不可缓存）。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    result = await db.execute(
        select(CloudComputerUser)
        .where(CloudComputerUser.owner_id == user.id)
        .order_by(CloudComputerUser.created_at.desc())
    )
    cloud_computers = result.scalars().all()

    html = await render_template("my_cloud_computers.html", cloud_computers=cloud_computers)
    return fragment_response(html, request=request)
