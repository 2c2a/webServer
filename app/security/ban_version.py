"""ban_version 机制：无状态秒级令牌撤销。

原理：
- 用户表存储 ban_version（整数，默认 0）
- Access Token JWT Payload 携带签发时的 ban_version（bv 字段）
- 每次请求验签后，比对 JWT 中的 bv 与数据库当前 ban_version
- 封禁用户时递增数据库 ban_version，旧令牌立即失效
- 无需 Redis 黑名单，实现无状态秒级撤销

注意：递增 ban_version 也会使该用户所有已签发令牌失效（包括合法会话），
因此仅用于封禁/强制下线场景。普通登出由前端清除内存令牌即可。
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_ban_version(db: AsyncSession, user_id: int) -> int:
    """获取用户当前 ban_version。"""
    result = await db.execute(
        select(User.ban_version).where(User.id == user_id)
    )
    row = result.first()
    return row[0] if row else 0


async def increment_ban_version(db: AsyncSession, user_id: int) -> int:
    """递增用户 ban_version，使所有已签发令牌失效。

    返回递增后的新版本号。
    """
    # 原子递增
    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(ban_version=User.ban_version + 1)
    )
    await db.commit()
    new_ver = await get_ban_version(db, user_id)
    return new_ver


def is_token_revoked(jwt_ban_version: int, db_ban_version: int) -> bool:
    """判断令牌是否已撤销：JWT 中的版本 < 数据库当前版本即撤销。"""
    return jwt_ban_version < db_ban_version
