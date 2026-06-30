"""产品组管理 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_staff
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models.operations import ProductGroup
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/product-groups", tags=["product-groups"])


class ProductGroupOut(BaseModel):
    id: int
    name: str
    description: str | None
    display_order: int
    is_active: bool
    visibility: str

    model_config = {"from_attributes": True}


class ProductGroupCreate(BaseModel):
    name: str
    description: str | None = None
    display_order: int = 0
    is_active: bool = True
    visibility: str = "public"


class ProductGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    display_order: int | None = None
    is_active: bool | None = None
    visibility: str | None = None


async def _apply_site_group_filter(query, tenant: TenantContext, user):
    """非超级用户按站点组过滤。"""
    if tenant.site_group_id and not user.is_superuser:
        return query.where(
            (ProductGroup.site_group_id == tenant.site_group_id)
            | (ProductGroup.site_group_id.is_(None))
        )
    return query


@router.get("", response_model=list[ProductGroupOut])
async def list_product_groups(
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """列出产品组。"""
    query = select(ProductGroup).order_by(ProductGroup.display_order, ProductGroup.id)
    query = await _apply_site_group_filter(query, tenant, user)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=ProductGroupOut, status_code=201)
async def create_product_group(
    body: ProductGroupCreate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """创建产品组。"""
    pg = ProductGroup(
        name=body.name,
        description=body.description,
        display_order=body.display_order,
        is_active=body.is_active,
        visibility=body.visibility,
        site_group_id=tenant.site_group_id,
        created_by_id=user.id,
    )
    db.add(pg)
    await db.commit()
    await db.refresh(pg)
    return pg


@router.get("/{pg_id}", response_model=ProductGroupOut)
async def get_product_group(
    pg_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """获取产品组详情。"""
    query = select(ProductGroup).where(ProductGroup.id == pg_id)
    query = await _apply_site_group_filter(query, tenant, user)
    result = await db.execute(query)
    pg = result.scalar_one_or_none()
    if pg is None:
        raise NotFoundError("产品组不存在")
    return pg


@router.put("/{pg_id}", response_model=ProductGroupOut)
async def update_product_group(
    pg_id: int,
    body: ProductGroupUpdate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """更新产品组。"""
    query = select(ProductGroup).where(ProductGroup.id == pg_id)
    query = await _apply_site_group_filter(query, tenant, user)
    result = await db.execute(query)
    pg = result.scalar_one_or_none()
    if pg is None:
        raise NotFoundError("产品组不存在")

    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(pg, key, value)

    await db.commit()
    await db.refresh(pg)
    return pg


@router.delete("/{pg_id}")
async def delete_product_group(
    pg_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """删除产品组。"""
    query = select(ProductGroup).where(ProductGroup.id == pg_id)
    query = await _apply_site_group_filter(query, tenant, user)
    result = await db.execute(query)
    pg = result.scalar_one_or_none()
    if pg is None:
        raise NotFoundError("产品组不存在")
    await db.delete(pg)
    await db.commit()
    return {"success": True}
