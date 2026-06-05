"""
主题和页面内容管理路由

包含主题配置、页面内容管理及管理页面
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import DBSession, PaginationParams, StaffUser
from app.models.theme import PageContent, ThemeConfig
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.theme import (
    PageContentResponse,
    PageContentUpdate,
    ThemeConfigResponse,
    ThemeConfigUpdate,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ========== 主题配置 API ==========


@router.get(
    "/api/theme",
    response_model=APIResponse[ThemeConfigResponse],
    tags=["themes"],
)
async def get_theme_config(
    db: DBSession = ...,
):
    """获取当前主题配置"""
    result = await db.execute(select(ThemeConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = ThemeConfig(id=1)
        db.add(config)
        await db.flush()

    return APIResponse(data=ThemeConfigResponse.model_validate(config))


@router.put(
    "/api/theme",
    response_model=APIResponse[ThemeConfigResponse],
    tags=["themes"],
)
async def update_theme_config(
    body: ThemeConfigUpdate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """更新主题配置（管理员）"""
    result = await db.execute(select(ThemeConfig).limit(1))
    config = result.scalar_one_or_none()

    if not config:
        config = ThemeConfig(id=1)
        db.add(config)

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    await db.flush()
    return APIResponse(data=ThemeConfigResponse.model_validate(config), message="主题配置已更新")


# ========== 页面内容 API ==========


@router.get(
    "/api/page-contents",
    response_model=APIResponse[PaginatedResponse[PageContentResponse]],
    tags=["themes"],
)
async def list_page_contents(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
):
    """列出页面内容"""
    count_stmt = select(func.count()).select_from(PageContent)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(PageContent)
        .order_by(PageContent.position)
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    contents = result.scalars().all()

    items = [PageContentResponse.model_validate(c) for c in contents]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.put(
    "/api/page-contents/{position}",
    response_model=APIResponse[PageContentResponse],
    tags=["themes"],
)
async def update_page_content(
    position: str,
    body: PageContentUpdate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """更新页面内容（管理员）"""
    result = await db.execute(
        select(PageContent).where(PageContent.position == position)
    )
    content = result.scalar_one_or_none()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"位置 '{position}' 的页面内容不存在",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(content, field, value)

    await db.flush()
    return APIResponse(
        data=PageContentResponse.model_validate(content),
        message="页面内容已更新",
    )


# ========== 主题管理页面 ==========


@router.get("/admin/themes", tags=["themes-pages"])
async def admin_themes_page(
    request: Request,
    user: StaffUser,
):
    """主题管理页面"""
    return templates.TemplateResponse("admin_base/themes/themeconfig_edit.html", {
        "request": request,
        "user": user,
    })
