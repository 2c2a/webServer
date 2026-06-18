"""认证路由：登录、注册、刷新、登出。

- 登录：验证 BLAKE2b 预哈希 + Argon2id，签发 Ed25519 JWT（内存）+ AES-GCM Refresh（Cookie）
- 刷新：用 Refresh Token 换取新 Access Token（滑动窗口）
- 登出：清除 Refresh Cookie（前端清除内存 Access Token）
- 注册：BLAKE2b 预哈希 + Argon2id 存储
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    RegisterRequest,
    UserInfo,
)
from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import AppError, AuthError, RateLimitError
from app.core.logging import get_logger
from app.models.user import User, UserProfile
from app.security.jwt_auth import issue_access_token
from app.security.password import hash_password, needs_rehash, verify_password
from app.security.refresh_token import (
    clear_refresh_cookie,
    decode_refresh_token,
    issue_refresh_token,
    set_refresh_cookie,
)
from app.tenant.dependencies import get_client_ip, get_tenant
from app.tenant.resolver import TenantContext

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """用户登录。

    前端先对密码做 BLAKE2b 预哈希（防 DoS），后端 Argon2id 验证。
    成功后签发 Ed25519 JWT（5 分钟，前端内存）+ AES-GCM Refresh（7 天，HttpOnly Cookie）。
    """
    ip = get_client_ip(request)
    # TODO: 速率限制（基于 Redis）

    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password_prehash, user.password_hash):
        log.info("login_failed", username=body.username, ip=ip)
        raise AuthError("用户名或密码错误")

    if not user.is_active:
        raise AuthError("账号已被禁用")

    # 检查封禁
    if user.active_ban is not None:
        raise AuthError("账号已被封禁")

    # Argon2id 参数升级时重新哈希
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password_prehash)
        await db.commit()

    # 签发令牌
    access_token = issue_access_token(
        user_id=user.id,
        username=user.username,
        ban_version=user.ban_version,
        site_group_id=tenant.site_group_id,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
    )
    refresh_token = issue_refresh_token(
        user_id=user.id,
        ban_version=user.ban_version,
        site_group_id=tenant.site_group_id,
    )
    set_refresh_cookie(response, refresh_token)

    log.info("login_success", user_id=user.id, username=user.username, ip=ip)
    return LoginResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        username=user.username,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
    )


@router.post("/register", response_model=LoginResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """用户注册。"""
    # 检查用户名是否已存在
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise AppError("用户名已存在", "username_exists")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password_prehash),
        is_active=True,
        is_verified=False,
    )
    db.add(user)
    await db.flush()
    # 创建空 profile
    db.add(UserProfile(user_id=user.id))
    await db.commit()

    access_token = issue_access_token(
        user_id=user.id,
        username=user.username,
        ban_version=user.ban_version,
        site_group_id=tenant.site_group_id,
    )
    refresh_token = issue_refresh_token(
        user_id=user.id, ban_version=user.ban_version, site_group_id=tenant.site_group_id
    )
    set_refresh_cookie(response, refresh_token)

    log.info("register_success", user_id=user.id, username=user.username)
    return LoginResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        username=user.username,
        is_superuser=False,
        is_staff=False,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """用 Refresh Token 换取新 Access Token（滑动窗口轮换）。"""
    cookie_token = request.cookies.get(settings.refresh_token_cookie_name, "")
    payload = decode_refresh_token(cookie_token)
    if payload is None:
        raise AuthError("Refresh Token 无效或已过期")

    user_id = int(payload["sub"])
    jwt_bv = int(payload.get("bv", 0))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        clear_refresh_cookie(response)
        raise AuthError("用户不存在或已禁用")

    # ban_version 校验
    from app.security.ban_version import is_token_revoked

    if is_token_revoked(jwt_bv, user.ban_version):
        clear_refresh_cookie(response)
        raise AuthError("令牌已撤销，请重新登录")

    # 签发新 Access Token
    access_token = issue_access_token(
        user_id=user.id,
        username=user.username,
        ban_version=user.ban_version,
        site_group_id=payload.get("sg"),
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
    )
    # 轮换 Refresh Token（滑动窗口）
    new_refresh = issue_refresh_token(
        user_id=user.id,
        ban_version=user.ban_version,
        site_group_id=payload.get("sg"),
    )
    set_refresh_cookie(response, new_refresh)

    return RefreshResponse(access_token=access_token, expires_in=settings.access_token_ttl_seconds)


@router.post("/logout")
async def logout(response: Response):
    """登出：清除 Refresh Cookie（前端清除内存 Access Token）。"""
    clear_refresh_cookie(response)
    return {"success": True}


@router.get("/me", response_model=UserInfo)
async def me(user=Depends(get_current_user)):
    """获取当前用户信息。"""
    return UserInfo(
        id=user.id,
        username=user.username,
        email=user.db_user.email if user.db_user else None,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        is_verified=user.db_user.is_verified if user.db_user else False,
    )


@router.post("/password")
async def change_password(
    body: ChangePasswordRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码。"""
    if user.db_user is None:
        raise AuthError()
    if not verify_password(body.old_password_prehash, user.db_user.password_hash):
        raise AuthError("原密码错误")
    user.db_user.password_hash = hash_password(body.new_password_prehash)
    await db.commit()
    return {"success": True}
