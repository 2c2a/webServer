"""
供应商仪表盘和管理路由

包含供应商仪表盘、主机列表、产品列表页面
"""
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import DBSession, ProviderUser
from app.models.host import Host
from app.models.product import Product

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/provider/", tags=["provider-pages"])
async def provider_dashboard(
    request: Request,
    user: ProviderUser,
    db: DBSession,
):
    """供应商仪表盘"""
    # 获取供应商关联的主机和产品统计
    host_count = (
        await db.execute(
            select(func.count())
            .select_from(Host)
            .where(Host.providers.any(id=user.id))
        )
    ).scalar() or 0

    product_count = (
        await db.execute(select(func.count()).select_from(Product))
    ).scalar() or 0

    return templates.TemplateResponse("admin_base/provider/dashboard.html", {
        "request": request,
        "user": user,
        "stats": {
            "host_count": host_count,
            "product_count": product_count,
        },
    })


@router.get("/provider/hosts", tags=["provider-pages"])
async def provider_hosts_page(
    request: Request,
    user: ProviderUser,
):
    """供应商主机列表页面"""
    return templates.TemplateResponse("admin_base/providers/host_list.html", {
        "request": request,
        "user": user,
    })


@router.get("/provider/products", tags=["provider-pages"])
async def provider_products_page(
    request: Request,
    user: ProviderUser,
):
    """供应商产品列表页面"""
    return templates.TemplateResponse("admin_base/operations/product_list.html", {
        "request": request,
        "user": user,
    })
