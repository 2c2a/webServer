"""
仪表盘和系统配置路由

包含首页仪表盘、统计数据、系统配置、站点组管理
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession, PaginationParams, StaffUser
from app.models.dashboard import SiteGroup, SystemConfig
from app.models.host import Host
from app.models.product import AccountOpeningRequest, CloudComputerUser, Product
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.dashboard import (
    SiteGroupCreate,
    SiteGroupResponse,
    SystemConfigResponse,
    SystemConfigUpdate,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ========== 仪表盘页面 ==========


@router.get("/", tags=["dashboard-pages"])
async def dashboard_index(
    request: Request,
    user: CurrentUser,
    db: DBSession,
):
    """仪表盘首页"""
    # 获取统计数据
    host_count = (await db.execute(select(func.count()).select_from(Host))).scalar() or 0
    product_count = (await db.execute(select(func.count()).select_from(Product))).scalar() or 0
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    pending_requests = (
        await db.execute(
            select(func.count()).select_from(AccountOpeningRequest).where(
                AccountOpeningRequest.status == "pending"
            )
        )
    ).scalar() or 0

    return templates.TemplateResponse("dashboard/index.html", {
        "request": request,
        "user": user,
        "stats": {
            "host_count": host_count,
            "product_count": product_count,
            "user_count": user_count,
            "pending_requests": pending_requests,
        },
    })


# ========== 仪表盘 API ==========


@router.get("/api/dashboard/stats", response_model=APIResponse, tags=["dashboard"])
async def dashboard_stats(
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """仪表盘统计数据"""
    host_count = (await db.execute(select(func.count()).select_from(Host))).scalar() or 0
    product_count = (await db.execute(select(func.count()).select_from(Product))).scalar() or 0
    user_count = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    cloud_user_count = (
        await db.execute(select(func.count()).select_from(CloudComputerUser))
    ).scalar() or 0
    ticket_count = (await db.execute(select(func.count()).select_from(Ticket))).scalar() or 0
    pending_requests = (
        await db.execute(
            select(func.count()).select_from(AccountOpeningRequest).where(
                AccountOpeningRequest.status == "pending"
            )
        )
    ).scalar() or 0

    online_hosts = (
        await db.execute(
            select(func.count()).select_from(Host).where(Host.status == "online")
        )
    ).scalar() or 0

    return APIResponse(data={
        "host_count": host_count,
        "online_hosts": online_hosts,
        "product_count": product_count,
        "user_count": user_count,
        "cloud_user_count": cloud_user_count,
        "ticket_count": ticket_count,
        "pending_requests": pending_requests,
    })


# ========== 管理员仪表盘页面 ==========


@router.get("/admin/dashboard", tags=["dashboard-pages"])
async def admin_dashboard_page(
    request: Request,
    user: StaffUser,
):
    """管理员仪表盘页面"""
    return templates.TemplateResponse("admin_base/dashboard.html", {
        "request": request,
        "user": user,
    })


@router.get("/admin/system-config", tags=["dashboard-pages"])
async def admin_system_config_page(
    request: Request,
    user: StaffUser,
    db: DBSession,
):
    """系统配置页面"""
    result = await db.execute(select(SystemConfig).limit(1))
    config = result.scalar_one_or_none()

    return templates.TemplateResponse("dashboard/system_config.html", {
        "request": request,
        "user": user,
        "config": config,
    })


# ========== 系统配置 API ==========


@router.put(
    "/api/system-config",
    response_model=APIResponse[SystemConfigResponse],
    tags=["system-config"],
)
async def update_system_config(
    body: SystemConfigUpdate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """更新系统配置"""
    result = await db.execute(select(SystemConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = SystemConfig(id=1)
        db.add(config)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    await db.flush()
    return APIResponse(data=SystemConfigResponse.model_validate(config), message="系统配置已更新")


# ========== 站点组 API ==========


@router.get(
    "/api/site-groups",
    response_model=APIResponse[PaginatedResponse[SiteGroupResponse]],
    tags=["site-groups"],
)
async def list_site_groups(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """列出站点组"""
    count_stmt = select(func.count()).select_from(SiteGroup)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(SiteGroup)
        .order_by(SiteGroup.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    groups = result.scalars().all()

    items = [SiteGroupResponse.model_validate(g) for g in groups]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/api/site-groups",
    response_model=APIResponse[SiteGroupResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["site-groups"],
)
async def create_site_group(
    body: SiteGroupCreate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """创建站点组"""
    group = SiteGroup(
        id=str(uuid4()),
        name=body.name,
        slug=body.slug,
        description=body.description,
        site_name=body.site_name,
        site_icon=body.site_icon,
        is_active=body.is_active,
    )
    db.add(group)
    await db.flush()
    return APIResponse(data=SiteGroupResponse.model_validate(group), message="站点组创建成功")
