"""
FastAPI 依赖注入

提供认证、数据库会话、分页等通用依赖
"""
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import Group, User, user_groups
from app.services.auth import AuthService

# ========== 认证依赖 ==========

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Optional[User]:
    """获取当前用户（可选，未登录返回 None）"""
    # 1. 尝试 JWT Bearer token
    if credentials:
        payload = AuthService.verify_token(credentials.credentials)
        if payload:
            user_id = payload.get("sub")
            if user_id:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
                if user and user.is_active:
                    return user

    # 2. 尝试 session cookie
    session_id = request.cookies.get("2c2a_session")
    if session_id:
        user_id = await AuthService.get_session_user_id(session_id)
        if user_id:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user and user.is_active:
                return user

    return None


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """获取当前用户（必须登录）"""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期",
        )
    return user


async def get_staff_user(
    user: User = Depends(get_current_user),
) -> User:
    """要求 staff 权限"""
    if not user.is_staff and not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user


async def get_superuser(
    user: User = Depends(get_current_user),
) -> User:
    """要求超级管理员权限"""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return user


async def get_provider_user(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """要求提供商权限（属于'主机提供商'组且非超级管理员）"""
    if user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="超级管理员请使用管理后台",
        )
    stmt = select(exists().where(
        user_groups.c.user_id == user.id,
        Group.id == user_groups.c.group_id,
        Group.name == "主机提供商",
    ))
    result = await db.execute(stmt)
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要提供商权限",
        )
    return user


# ========== 分页依赖 ==========

class PaginationParams:
    def __init__(self, page: int = 1, page_size: int = 20):
        self.page = max(1, page)
        self.page_size = min(100, max(1, page_size))

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


# ========== 类型别名 ==========

CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[Optional[User], Depends(get_current_user_optional)]
StaffUser = Annotated[User, Depends(get_staff_user)]
Superuser = Annotated[User, Depends(get_superuser)]
ProviderUser = Annotated[User, Depends(get_provider_user)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
