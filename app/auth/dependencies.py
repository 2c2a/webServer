"""认证依赖注入：从请求中解析当前用户。

流程：
- Access Token 从 Authorization: Bearer 头读取（前端内存存储，通过 JS 发送）
- Ed25519 验签 + 过期校验
- ban_version 校验（无状态秒级撤销）
- Refresh Token 从 HttpOnly Cookie 读取（用于 /auth/refresh 及页面刷新后的 HTMX 片段认证）
"""
from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import AuthError, ForbiddenError
from app.models.user import User
from app.security.ban_version import is_token_revoked
from app.security.jwt_auth import decode_access_token
from app.security.refresh_token import decode_refresh_token
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext


@dataclass
class CurrentUser:
    """当前认证用户上下文。"""

    id: int
    username: str
    is_superuser: bool
    is_staff: bool
    ban_version: int
    site_group_id: int | None
    db_user: User | None = None


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CurrentUser | None:
    """可选认证：有合法 Access Token 或 Refresh Cookie 时返回用户，否则返回 None。

    优先读取 Authorization: Bearer（前端内存 Access Token）；未提供时回退到
    HttpOnly Refresh Cookie，用于页面整刷后 HTMX 片段仍能识别用户。
    """
    payload = None

    # 1) Access Token（前端内存，通过 HTMX configRequest 注入 header）
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = decode_access_token(token)
        except jwt.PyJWTError:
            payload = None

    # 2) Refresh Cookie（HttpOnly，整页刷新后 Access Token 丢失时的兜底）
    if payload is None:
        refresh_token = request.cookies.get(settings.refresh_token_cookie_name, "")
        payload = decode_refresh_token(refresh_token)

    if payload is None:
        return None

    user_id = int(payload["sub"])
    jwt_bv = int(payload.get("bv", 0))

    # 查库校验 ban_version（无状态撤销）
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if is_token_revoked(jwt_bv, user.ban_version):
        return None  # 已封禁/强制下线

    return CurrentUser(
        id=user.id,
        username=user.username,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        ban_version=user.ban_version,
        site_group_id=payload.get("sg"),
        db_user=user,
    )


async def get_current_user(
    user: CurrentUser | None = Depends(get_current_user_optional),
) -> CurrentUser:
    """强制认证：无合法用户抛 401。"""
    if user is None:
        raise AuthError("请先登录")
    return user


async def require_staff(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """要求 staff 及以上权限。"""
    if not (user.is_staff or user.is_superuser):
        raise ForbiddenError("需要管理员权限")
    return user


async def require_superuser(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """要求超级管理员权限。"""
    if not user.is_superuser:
        raise ForbiddenError("需要超级管理员权限")
    return user


async def require_tenant_admin(
    user: CurrentUser = Depends(get_current_user),
    tenant: TenantContext = Depends(get_tenant),
) -> CurrentUser:
    """要求当前租户的管理员权限（超管或站点组管理员）。"""
    if user.is_superuser:
        return user
    if tenant.site_group_id and user.db_user:
        # 检查是否为该站点组管理员
        if tenant.site_group_id in [sg.id for sg in user.db_user.admin_site_groups]:
            return user
    raise ForbiddenError("需要站点组管理员权限")
