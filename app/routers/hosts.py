"""
主机和主机组 CRUD 路由

包含主机管理、主机组管理、WinRM 连接测试及管理页面
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession, PaginationParams, StaffUser
from app.models.host import Host, HostGroup
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.host import (
    HostCreate,
    HostGroupCreate,
    HostGroupResponse,
    HostResponse,
    HostUpdate,
)
from app.tasks.hosts import test_winrm_connection

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ========== 主机 API ==========


@router.get(
    "/api/hosts",
    response_model=APIResponse[PaginatedResponse[HostResponse]],
    tags=["hosts"],
)
async def list_hosts(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出主机（管理员）"""
    count_stmt = select(func.count()).select_from(Host)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Host)
        .order_by(Host.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    hosts = result.scalars().all()

    items = [HostResponse.model_validate(h) for h in hosts]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/api/hosts",
    response_model=APIResponse[HostResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["hosts"],
)
async def create_host(
    body: HostCreate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """创建主机（管理员）"""
    host = Host(
        id=str(uuid4()),
        name=body.name,
        hostname=body.hostname,
        connection_type=body.connection_type,
        auth_method=body.auth_method,
        port=body.port,
        rdp_port=body.rdp_port,
        use_ssl=body.use_ssl,
        username=body.username,
        description=body.description,
    )
    if body.password:
        from utils.crypto import encrypt_value
        host._password = encrypt_value(body.password)

    db.add(host)
    await db.flush()
    return APIResponse(data=HostResponse.model_validate(host), message="主机创建成功")


@router.get(
    "/api/hosts/{host_id}",
    response_model=APIResponse[HostResponse],
    tags=["hosts"],
)
async def get_host(
    host_id: str,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """获取主机详情"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")
    return APIResponse(data=HostResponse.model_validate(host))


@router.put(
    "/api/hosts/{host_id}",
    response_model=APIResponse[HostResponse],
    tags=["hosts"],
)
async def update_host(
    host_id: str,
    body: HostUpdate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """更新主机"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")

    update_data = body.model_dump(exclude_unset=True)
    if "password" in update_data and update_data["password"]:
        from utils.crypto import encrypt_value
        host._password = encrypt_value(update_data.pop("password"))
    else:
        update_data.pop("password", None)

    for field, value in update_data.items():
        setattr(host, field, value)

    await db.flush()
    return APIResponse(data=HostResponse.model_validate(host), message="主机更新成功")


@router.delete(
    "/api/hosts/{host_id}",
    response_model=APIResponse,
    tags=["hosts"],
)
async def delete_host(
    host_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """删除主机"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")

    await db.delete(host)
    await db.flush()
    return APIResponse(message="主机已删除")


@router.post(
    "/api/hosts/{host_id}/test-connection",
    response_model=APIResponse,
    tags=["hosts"],
)
async def test_host_connection(
    host_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """测试主机 WinRM 连接（入队 Huey 任务）"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")

    task = test_winrm_connection(host_id)
    return APIResponse(
        data={"task_id": task.id},
        message="连接测试任务已提交",
    )


# ========== 主机组 API ==========


@router.get(
    "/api/host-groups",
    response_model=APIResponse[PaginatedResponse[HostGroupResponse]],
    tags=["host-groups"],
)
async def list_host_groups(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """列出主机组"""
    count_stmt = select(func.count()).select_from(HostGroup)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(HostGroup)
        .order_by(HostGroup.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    groups = result.scalars().all()

    items = [HostGroupResponse.model_validate(g) for g in groups]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/api/host-groups",
    response_model=APIResponse[HostGroupResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["host-groups"],
)
async def create_host_group(
    body: HostGroupCreate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """创建主机组"""
    group = HostGroup(
        id=str(uuid4()),
        name=body.name,
        description=body.description,
        created_by_id=user.id,
    )
    db.add(group)
    await db.flush()
    return APIResponse(data=HostGroupResponse.model_validate(group), message="主机组创建成功")


# ========== 主机管理页面 ==========


@router.get("/admin/hosts", tags=["hosts-pages"])
async def admin_hosts_page(
    request: Request,
    user: StaffUser,
):
    """主机管理页面"""
    return templates.TemplateResponse("admin_base/hosts/host_list.html", {
        "request": request,
        "user": user,
    })


@router.get("/admin/hosts/{host_id}", tags=["hosts-pages"])
async def admin_host_detail_page(
    request: Request,
    host_id: str,
    user: StaffUser,
    db: DBSession,
):
    """主机详情页面"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")

    return templates.TemplateResponse("admin_base/hosts/host_detail.html", {
        "request": request,
        "user": user,
        "host": host,
    })
