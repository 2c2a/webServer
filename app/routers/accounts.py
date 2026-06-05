"""
用户认证、注册、个人资料路由

包含登录/登出、注册、个人资料管理以及管理员用户管理
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import (
    CurrentUser,
    DBSession,
    PaginationParams,
    StaffUser,
    Superuser,
)
from app.models.user import Group, LoginLog, RegistrationLink, User, UserProfile
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.user import (
    LoginAPIResponse,
    LoginRequest,
    LoginResponse,
    PasswordChange,
    PasswordReset,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.auth import AuthService

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ========== 认证 API ==========


@router.post("/accounts/login", response_model=LoginAPIResponse, tags=["accounts"])
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: DBSession,
):
    """用户登录（设置 session cookie + 返回 JWT）"""
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    # 记录登录日志
    ip_address = request.client.host if request.client else ""
    user_agent = request.headers.get("user-agent", "")

    if not user or not AuthService.verify_password(body.password, user.password):
        # 记录失败日志
        if user:
            log = LoginLog(
                id=str(uuid4()),
                user_id=user.id,
                ip_address=ip_address,
                user_agent=user_agent,
                status="failed",
                failure_reason="密码错误",
            )
            db.add(log)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用",
        )

    # 创建 JWT
    access_token = AuthService.create_access_token(user.id)
    refresh_token = AuthService.create_refresh_token(user.id)

    # 创建 Redis 会话
    session_id = await AuthService.create_session(
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    # 设置 session cookie
    response.set_cookie(
        key="2c2a_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400 * 7,
    )

    # 更新最后登录信息
    user.last_login = datetime.now(timezone.utc)
    user.last_login_ip = ip_address

    # 记录成功日志
    log = LoginLog(
        id=str(uuid4()),
        user_id=user.id,
        ip_address=ip_address,
        user_agent=user_agent,
        status="success",
    )
    db.add(log)

    login_resp = LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )
    return LoginAPIResponse(data=login_resp)


@router.post("/accounts/logout", response_model=APIResponse, tags=["accounts"])
async def logout(
    request: Request,
    response: Response,
    user: CurrentUser,
):
    """用户登出（清除 session）"""
    session_id = request.cookies.get("2c2a_session")
    if session_id:
        await AuthService.destroy_session(session_id)

    response.delete_cookie(key="2c2a_session")
    return APIResponse(message="已成功登出")


@router.post(
    "/accounts/register",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["accounts"],
)
async def register(
    body: UserCreate,
    db: DBSession,
):
    """注册新用户"""
    # 检查用户名唯一性
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    # 检查邮箱唯一性
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="邮箱已被注册",
        )

    user = User(
        id=str(uuid4()),
        username=body.username,
        email=body.email,
        password=AuthService.hash_password(body.password),
        phone=body.phone,
    )
    db.add(user)

    # 创建用户资料
    profile = UserProfile(id=str(uuid4()), user_id=user.id)
    db.add(profile)

    # 分配默认用户组
    result = await db.execute(
        select(Group).join(Group.profile).where(Group.profile.has(is_default=True))
    )
    default_group = result.scalar_one_or_none()
    if default_group:
        user.groups.append(default_group)

    await db.flush()
    return APIResponse(data=UserResponse.model_validate(user), message="注册成功")


@router.get(
    "/accounts/profile",
    response_model=APIResponse[UserResponse],
    tags=["accounts"],
)
async def get_profile(user: CurrentUser):
    """获取当前用户资料（API）"""
    return APIResponse(data=UserResponse.model_validate(user))


@router.put(
    "/accounts/profile",
    response_model=APIResponse[UserResponse],
    tags=["accounts"],
)
async def update_profile(
    body: UserUpdate,
    user: CurrentUser,
    db: DBSession,
):
    """更新当前用户资料"""
    if body.email is not None:
        result = await db.execute(
            select(User).where(User.email == body.email, User.id != user.id)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="邮箱已被其他用户使用",
            )
        user.email = body.email

    if body.phone is not None:
        user.phone = body.phone
    if body.avatar is not None:
        user.avatar = body.avatar

    await db.flush()
    return APIResponse(data=UserResponse.model_validate(user), message="资料更新成功")


@router.post("/accounts/change-password", response_model=APIResponse, tags=["accounts"])
async def change_password(
    body: PasswordChange,
    user: CurrentUser,
    db: DBSession,
):
    """修改密码"""
    if not AuthService.verify_password(body.old_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )
    user.password = AuthService.hash_password(body.new_password)
    await db.flush()
    return APIResponse(message="密码修改成功")


@router.post(
    "/accounts/forgot-password",
    response_model=APIResponse,
    tags=["accounts"],
)
async def forgot_password(
    body: PasswordReset,
    db: DBSession,
):
    """请求密码重置"""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        # 不暴露用户是否存在
        return APIResponse(message="如果该邮箱已注册，将收到重置邮件")

    # TODO: 发送密码重置邮件
    return APIResponse(message="如果该邮箱已注册，将收到重置邮件")


# ========== 认证页面 ==========


@router.get("/accounts/login", tags=["accounts-pages"])
async def login_page(request: Request):
    """渲染登录页面"""
    return templates.TemplateResponse("accounts/login.html", {"request": request})


@router.get("/accounts/register", tags=["accounts-pages"])
async def register_page(request: Request):
    """渲染注册页面"""
    return templates.TemplateResponse("accounts/register.html", {"request": request})


@router.get("/accounts/profile", tags=["accounts-pages"])
async def profile_page(request: Request, user: CurrentUser):
    """渲染个人资料页面"""
    return templates.TemplateResponse("accounts/profile.html", {
        "request": request,
        "user": user,
    })


# ========== 管理员用户管理 ==========


@router.get(
    "/admin/accounts/users",
    response_model=APIResponse[PaginatedResponse[UserResponse]],
    tags=["admin-accounts"],
)
async def admin_list_users(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出用户（管理员）"""
    # 总数
    count_stmt = select(func.count()).select_from(User)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页查询
    stmt = (
        select(User)
        .order_by(User.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    items = [UserResponse.model_validate(u) for u in users]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/admin/accounts/users",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["admin-accounts"],
)
async def admin_create_user(
    body: UserCreate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """创建用户（管理员）"""
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已存在",
        )

    new_user = User(
        id=str(uuid4()),
        username=body.username,
        email=body.email,
        password=AuthService.hash_password(body.password),
        phone=body.phone,
    )
    db.add(new_user)
    await db.flush()
    return APIResponse(data=UserResponse.model_validate(new_user), message="用户创建成功")


@router.put(
    "/admin/accounts/users/{user_id}",
    response_model=APIResponse[UserResponse],
    tags=["admin-accounts"],
)
async def admin_update_user(
    user_id: str,
    body: UserUpdate,
    db: DBSession = ...,
    admin: StaffUser = ...,
):
    """更新用户（管理员）"""
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if body.email is not None:
        target_user.email = body.email
    if body.phone is not None:
        target_user.phone = body.phone
    if body.avatar is not None:
        target_user.avatar = body.avatar

    await db.flush()
    return APIResponse(data=UserResponse.model_validate(target_user), message="用户更新成功")


@router.delete(
    "/admin/accounts/users/{user_id}",
    response_model=APIResponse,
    tags=["admin-accounts"],
)
async def admin_delete_user(
    user_id: str,
    db: DBSession = ...,
    admin: Superuser = ...,
):
    """删除用户（超级管理员）"""
    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if target_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无法删除超级管理员",
        )

    await db.delete(target_user)
    await db.flush()
    return APIResponse(message="用户已删除")


@router.get(
    "/admin/accounts/groups",
    response_model=APIResponse[PaginatedResponse],
    tags=["admin-accounts"],
)
async def admin_list_groups(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出用户组（管理员）"""
    count_stmt = select(func.count()).select_from(Group)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Group)
        .order_by(Group.name)
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    groups = result.scalars().all()

    items = [{"id": g.id, "name": g.name} for g in groups]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.get(
    "/admin/accounts/reglinks",
    response_model=APIResponse[PaginatedResponse],
    tags=["admin-accounts"],
)
async def admin_list_reglinks(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出注册链接（管理员）"""
    count_stmt = select(func.count()).select_from(RegistrationLink)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(RegistrationLink)
        .order_by(RegistrationLink.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    links = result.scalars().all()

    items = [
        {
            "token": link.token,
            "group_id": link.group_id,
            "max_uses": link.max_uses,
            "used_count": link.used_count,
            "expires_at": link.expires_at.isoformat() if link.expires_at else None,
            "note": link.note,
        }
        for link in links
    ]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/admin/accounts/reglinks",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["admin-accounts"],
)
async def admin_create_reglink(
    group_id: str,
    max_uses: int = 1,
    note: str = "",
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """创建注册链接（管理员）"""
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户组不存在")

    link = RegistrationLink(
        token=str(uuid4()),
        group_id=group_id,
        created_by_id=user.id,
        max_uses=max_uses,
        note=note,
    )
    db.add(link)
    await db.flush()
    return APIResponse(data={"token": link.token}, message="注册链接创建成功")
