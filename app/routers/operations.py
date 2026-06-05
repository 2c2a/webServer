"""
产品、开户请求、云计算机用户 CRUD 路由

包含产品管理、开户申请、云电脑用户管理及运营页面
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession, PaginationParams, StaffUser
from app.models.product import (
    AccountOpeningRequest,
    CloudComputerUser,
    Product,
)
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.product import (
    AccountOpeningRequestCreate,
    AccountOpeningRequestResponse,
    CloudComputerUserResponse,
    CloudComputerUserUpdate,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.tasks.operations import (
    process_opening_request,
    remote_remove_admin,
    remote_set_admin,
    reset_user_password,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ========== 产品 API ==========


@router.get(
    "/api/products",
    response_model=APIResponse[PaginatedResponse[ProductResponse]],
    tags=["products"],
)
async def list_products(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """列出产品"""
    count_stmt = select(func.count()).select_from(Product)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Product)
        .order_by(Product.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    products = result.scalars().all()

    items = [ProductResponse.model_validate(p) for p in products]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/api/products",
    response_model=APIResponse[ProductResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["products"],
)
async def create_product(
    body: ProductCreate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """创建产品（管理员）"""
    product = Product(
        id=str(uuid4()),
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        host_id=body.host_id,
        product_group_id=body.product_group_id,
        rdp_port=body.rdp_port,
        display_hostname=body.display_hostname,
        is_available=body.is_available,
        auto_approval=body.auto_approval,
        visibility=body.visibility,
        enable_disk_quota=body.enable_disk_quota,
        enable_host_protection=body.enable_host_protection,
        default_disk_quota=body.default_disk_quota,
        allow_extra_quota_disks=body.allow_extra_quota_disks,
        created_by_id=user.id,
    )
    db.add(product)
    await db.flush()
    return APIResponse(data=ProductResponse.model_validate(product), message="产品创建成功")


@router.get(
    "/api/products/{product_id}",
    response_model=APIResponse[ProductResponse],
    tags=["products"],
)
async def get_product(
    product_id: str,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """获取产品详情"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="产品不存在")
    return APIResponse(data=ProductResponse.model_validate(product))


@router.put(
    "/api/products/{product_id}",
    response_model=APIResponse[ProductResponse],
    tags=["products"],
)
async def update_product(
    product_id: str,
    body: ProductUpdate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """更新产品"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="产品不存在")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    await db.flush()
    return APIResponse(data=ProductResponse.model_validate(product), message="产品更新成功")


@router.delete(
    "/api/products/{product_id}",
    response_model=APIResponse,
    tags=["products"],
)
async def delete_product(
    product_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """删除产品"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="产品不存在")

    await db.delete(product)
    await db.flush()
    return APIResponse(message="产品已删除")


# ========== 开户请求 API ==========


@router.get(
    "/api/opening-requests",
    response_model=APIResponse[PaginatedResponse[AccountOpeningRequestResponse]],
    tags=["opening-requests"],
)
async def list_opening_requests(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """列出开户请求"""
    count_stmt = select(func.count()).select_from(AccountOpeningRequest)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(AccountOpeningRequest)
        .order_by(AccountOpeningRequest.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    requests = result.scalars().all()

    items = [AccountOpeningRequestResponse.model_validate(r) for r in requests]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/api/opening-requests",
    response_model=APIResponse[AccountOpeningRequestResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["opening-requests"],
)
async def submit_opening_request(
    body: AccountOpeningRequestCreate,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """提交开户请求"""
    opening_request = AccountOpeningRequest(
        id=str(uuid4()),
        applicant_id=user.id,
        target_product_id=body.target_product_id,
        username=body.username,
        user_fullname=body.user_fullname,
        user_email=body.user_email,
        user_description=body.user_description,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        requested_disk_capacity=body.requested_disk_capacity,
        status="pending",
    )
    db.add(opening_request)
    await db.flush()
    return APIResponse(
        data=AccountOpeningRequestResponse.model_validate(opening_request),
        message="开户请求已提交",
    )


@router.post(
    "/api/opening-requests/{request_id}/approve",
    response_model=APIResponse,
    tags=["opening-requests"],
)
async def approve_opening_request(
    request_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """批准开户请求（管理员）"""
    result = await db.execute(
        select(AccountOpeningRequest).where(AccountOpeningRequest.id == request_id)
    )
    opening_request = result.scalar_one_or_none()
    if not opening_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="请求不存在")

    if opening_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能批准待处理的请求",
        )

    opening_request.status = "approved"
    await db.flush()

    # 异步处理开户
    process_opening_request(request_id, operator_id=user.id)

    return APIResponse(message="开户请求已批准，正在处理")


@router.post(
    "/api/opening-requests/{request_id}/reject",
    response_model=APIResponse,
    tags=["opening-requests"],
)
async def reject_opening_request(
    request_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """拒绝开户请求（管理员）"""
    result = await db.execute(
        select(AccountOpeningRequest).where(AccountOpeningRequest.id == request_id)
    )
    opening_request = result.scalar_one_or_none()
    if not opening_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="请求不存在")

    if opening_request.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能拒绝待处理的请求",
        )

    opening_request.status = "rejected"
    await db.flush()
    return APIResponse(message="开户请求已拒绝")


@router.post(
    "/api/opening-requests/{request_id}/retry",
    response_model=APIResponse,
    tags=["opening-requests"],
)
async def retry_opening_request(
    request_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """重试失败的开户请求"""
    result = await db.execute(
        select(AccountOpeningRequest).where(AccountOpeningRequest.id == request_id)
    )
    opening_request = result.scalar_one_or_none()
    if not opening_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="请求不存在")

    if opening_request.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能重试失败的请求",
        )

    opening_request.status = "pending"
    opening_request.retry_count += 1
    await db.flush()

    process_opening_request(request_id, operator_id=user.id)
    return APIResponse(message="正在重试开户请求")


# ========== 云电脑用户 API ==========


@router.get(
    "/api/cloud-users",
    response_model=APIResponse[PaginatedResponse[CloudComputerUserResponse]],
    tags=["cloud-users"],
)
async def list_cloud_users(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """列出云电脑用户"""
    count_stmt = select(func.count()).select_from(CloudComputerUser)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(CloudComputerUser)
        .order_by(CloudComputerUser.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    cloud_users = result.scalars().all()

    items = [CloudComputerUserResponse.model_validate(u) for u in cloud_users]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.put(
    "/api/cloud-users/{user_id}",
    response_model=APIResponse[CloudComputerUserResponse],
    tags=["cloud-users"],
)
async def update_cloud_user(
    user_id: str,
    body: CloudComputerUserUpdate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """更新云电脑用户"""
    result = await db.execute(
        select(CloudComputerUser).where(CloudComputerUser.id == user_id)
    )
    cloud_user = result.scalar_one_or_none()
    if not cloud_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(cloud_user, field, value)

    await db.flush()
    return APIResponse(
        data=CloudComputerUserResponse.model_validate(cloud_user),
        message="用户更新成功",
    )


@router.post(
    "/api/cloud-users/{user_id}/toggle-admin",
    response_model=APIResponse,
    tags=["cloud-users"],
)
async def toggle_cloud_user_admin(
    user_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """切换云电脑用户管理员状态"""
    result = await db.execute(
        select(CloudComputerUser).where(CloudComputerUser.id == user_id)
    )
    cloud_user = result.scalar_one_or_none()
    if not cloud_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if cloud_user.is_admin:
        remote_remove_admin(user_id, operator_id=user.id)
        return APIResponse(message="正在移除管理员权限")
    else:
        remote_set_admin(user_id, operator_id=user.id)
        return APIResponse(message="正在设置管理员权限")


@router.post(
    "/api/cloud-users/{user_id}/reset-password",
    response_model=APIResponse,
    tags=["cloud-users"],
)
async def reset_cloud_user_password(
    user_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """重置云电脑用户密码"""
    result = await db.execute(
        select(CloudComputerUser).where(CloudComputerUser.id == user_id)
    )
    cloud_user = result.scalar_one_or_none()
    if not cloud_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    reset_user_password(user_id, operator_id=user.id)
    return APIResponse(message="密码重置任务已提交")


# ========== 运营页面 ==========


@router.get("/operations/", tags=["operations-pages"])
async def operations_page(
    request: Request,
    user: CurrentUser,
):
    """运营页面"""
    return templates.TemplateResponse("operations/account_opening_request_list.html", {
        "request": request,
        "user": user,
    })


@router.get("/operations/my-cloud-computers", tags=["operations-pages"])
async def my_cloud_computers_page(
    request: Request,
    user: CurrentUser,
):
    """我的云电脑页面"""
    return templates.TemplateResponse("operations/my_cloud_computers.html", {
        "request": request,
        "user": user,
    })
