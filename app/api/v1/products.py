"""产品管理 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_staff
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models.host import Host
from app.models.operations import Product, ProductGroup
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/products", tags=["products"])


class ProductOut(BaseModel):
    id: int
    name: str
    description: str | None
    display_name: str | None
    display_description: str | None
    product_group_id: int | None
    host_id: int
    site_group_id: int | None
    rdp_port: int
    display_hostname: str | None
    is_available: bool
    auto_approval: bool
    visibility: str
    limit_one_per_user: bool
    required_points: int

    model_config = {"from_attributes": True}


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    display_name: str | None = None
    display_description: str | None = None
    product_group_id: int | None = None
    host_id: int
    rdp_port: int = 3389
    display_hostname: str | None = None
    is_available: bool = True
    auto_approval: bool = False
    visibility: str = "public"
    limit_one_per_user: bool = False
    required_points: int = 0


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    display_name: str | None = None
    display_description: str | None = None
    product_group_id: int | None = None
    host_id: int | None = None
    rdp_port: int | None = None
    display_hostname: str | None = None
    is_available: bool | None = None
    auto_approval: bool | None = None
    visibility: str | None = None
    limit_one_per_user: bool | None = None
    required_points: int | None = None


async def _apply_site_group_filter(query, tenant: TenantContext, user, model):
    """非超级用户按站点组过滤。"""
    if tenant.site_group_id and not user.is_superuser:
        return query.where(
            (model.site_group_id == tenant.site_group_id)
            | (model.site_group_id.is_(None))
        )
    return query


@router.get("", response_model=list[ProductOut])
async def list_products(
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """列出产品。"""
    query = select(Product).order_by(Product.id.desc())
    query = await _apply_site_group_filter(query, tenant, user, Product)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """创建产品。"""
    # 校验主机存在且在当前站点组
    host_filters = [Host.id == body.host_id]
    if tenant.site_group_id and not user.is_superuser:
        host_filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    host_result = await db.execute(select(Host).where(*host_filters))
    if host_result.scalar_one_or_none() is None:
        raise NotFoundError("主机不存在")

    # 校验产品组
    if body.product_group_id is not None:
        pg_filters = [ProductGroup.id == body.product_group_id]
        if tenant.site_group_id and not user.is_superuser:
            pg_filters.append(
                (ProductGroup.site_group_id == tenant.site_group_id)
                | (ProductGroup.site_group_id.is_(None))
            )
        pg_result = await db.execute(select(ProductGroup).where(*pg_filters))
        if pg_result.scalar_one_or_none() is None:
            raise NotFoundError("产品组不存在")

    product = Product(
        name=body.name,
        description=body.description,
        display_name=body.display_name,
        display_description=body.display_description,
        product_group_id=body.product_group_id,
        host_id=body.host_id,
        site_group_id=tenant.site_group_id,
        rdp_port=body.rdp_port,
        display_hostname=body.display_hostname,
        is_available=body.is_available,
        auto_approval=body.auto_approval,
        visibility=body.visibility,
        limit_one_per_user=body.limit_one_per_user,
        required_points=body.required_points,
        created_by_id=user.id,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """获取产品详情。"""
    query = select(Product).where(Product.id == product_id)
    query = await _apply_site_group_filter(query, tenant, user, Product)
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("产品不存在")
    return product


@router.put("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: int,
    body: ProductUpdate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """更新产品。"""
    query = select(Product).where(Product.id == product_id)
    query = await _apply_site_group_filter(query, tenant, user, Product)
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("产品不存在")

    update_data = body.model_dump(exclude_unset=True)

    # 校验主机
    if "host_id" in update_data and update_data["host_id"] is not None:
        host_filters = [Host.id == update_data["host_id"]]
        if tenant.site_group_id and not user.is_superuser:
            host_filters.append(
                (Host.site_group_id == tenant.site_group_id)
                | (Host.site_group_id.is_(None))
            )
        host_result = await db.execute(select(Host).where(*host_filters))
        if host_result.scalar_one_or_none() is None:
            raise NotFoundError("主机不存在")

    # 校验产品组
    if "product_group_id" in update_data and update_data["product_group_id"] is not None:
        pg_filters = [ProductGroup.id == update_data["product_group_id"]]
        if tenant.site_group_id and not user.is_superuser:
            pg_filters.append(
                (ProductGroup.site_group_id == tenant.site_group_id)
                | (ProductGroup.site_group_id.is_(None))
            )
        pg_result = await db.execute(select(ProductGroup).where(*pg_filters))
        if pg_result.scalar_one_or_none() is None:
            raise NotFoundError("产品组不存在")

    for key, value in update_data.items():
        setattr(product, key, value)

    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/{product_id}")
async def delete_product(
    product_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """删除产品。"""
    query = select(Product).where(Product.id == product_id)
    query = await _apply_site_group_filter(query, tenant, user, Product)
    result = await db.execute(query)
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("产品不存在")
    await db.delete(product)
    await db.commit()
    return {"success": True}
