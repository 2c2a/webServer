"""站内信服务：创建、查询、标记已读、删除、广播。

所有站内信写入必须通过此模块，保证 site_group_id 注入与字段一致性。
查询统一按 (user_id, site_group_id) 过滤，与积分模块保持一致的隔离模式。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.notification import Notification
from app.notifications.types import NotificationLevel, NotificationType, TYPE_META

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 创建
# ──────────────────────────────────────────────


async def create_notification(
    db: AsyncSession,
    *,
    user_id: int,
    type: str,
    title: str,
    content: str,
    level: str = NotificationLevel.INFO,
    body: str | None = None,
    icon: str | None = None,
    ref_type: str | None = None,
    ref_id: int | None = None,
    action_url: str | None = None,
    site_group_id: int | None = None,
) -> Notification:
    """创建单条站内信。

    若未显式提供 level / icon，则按 type 从 TYPE_META 取默认值。
    """
    default_level = NotificationLevel.INFO
    if type in TYPE_META:
        default_level = TYPE_META[type][1]
    if level == NotificationLevel.INFO and default_level != NotificationLevel.INFO:
        level = default_level

    notif = Notification(
        user_id=user_id,
        type=type,
        level=level,
        title=title,
        content=content,
        body=body,
        icon=icon,
        ref_type=ref_type,
        ref_id=ref_id,
        action_url=action_url,
        is_read=False,
        site_group_id=site_group_id,
    )
    db.add(notif)
    await db.flush()
    return notif


async def broadcast_notification(
    db: AsyncSession,
    *,
    type: str,
    title: str,
    content: str,
    level: str = NotificationLevel.INFO,
    body: str | None = None,
    icon: str | None = None,
    ref_type: str | None = None,
    ref_id: int | None = None,
    action_url: str | None = None,
    site_group_id: int | None = None,
    user_ids: list[int] | None = None,
) -> int:
    """广播站内信。

    user_ids=None 表示发送给站点组下全体用户（需调用方查询用户列表后传入），
    service 层不直接做全表扫描，避免与用户隔离策略耦合。
    返回创建条数。
    """
    if not user_ids:
        return 0

    count = 0
    for uid in user_ids:
        await create_notification(
            db,
            user_id=uid,
            type=type,
            title=title,
            content=content,
            level=level,
            body=body,
            icon=icon,
            ref_type=ref_type,
            ref_id=ref_id,
            action_url=action_url,
            site_group_id=site_group_id,
        )
        count += 1
    return count


# ──────────────────────────────────────────────
# 查询
# ──────────────────────────────────────────────


def _user_filters(user_id: int, site_group_id: int | None):
    """构建用户 + 站点隔离过滤条件（与积分模块一致）。"""
    filters = [Notification.user_id == user_id]
    if site_group_id:
        filters.append(
            (Notification.site_group_id == site_group_id)
            | (Notification.site_group_id.is_(None))
        )
    return filters


async def get_user_notifications(
    db: AsyncSession,
    user_id: int,
    *,
    filter: str = "all",
    site_group_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    """查询用户站内信列表。

    filter 可选：all / unread / system / ticket / points / security / product / maintenance
    """
    filters = _user_filters(user_id, site_group_id)

    if filter == "unread":
        filters.append(Notification.is_read == False)  # noqa: E712
    elif filter in (
        NotificationType.SYSTEM,
        NotificationType.TICKET,
        NotificationType.POINTS,
        NotificationType.SECURITY,
        NotificationType.PRODUCT,
        NotificationType.MAINTENANCE,
    ):
        filters.append(Notification.type == filter)

    result = await db.execute(
        select(Notification)
        .where(*filters)
        .order_by(Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_unread_count(
    db: AsyncSession, user_id: int, *, site_group_id: int | None = None
) -> int:
    """查询用户未读数。"""
    filters = _user_filters(user_id, site_group_id)
    filters.append(Notification.is_read == False)  # noqa: E712
    result = await db.execute(
        select(func.count(Notification.id)).where(*filters)
    )
    return int(result.scalar() or 0)


# ──────────────────────────────────────────────
# 已读与删除
# ──────────────────────────────────────────────


async def mark_as_read(
    db: AsyncSession, notification_id: int, user_id: int
) -> Notification:
    """标记单条已读（校验归属，幂等）。"""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        raise NotFoundError("站内信不存在")
    if not notif.is_read:
        notif.is_read = True
        notif.read_at = datetime.now(timezone.utc)
        await db.flush()
    return notif


async def mark_all_as_read(
    db: AsyncSession, user_id: int, *, site_group_id: int | None = None
) -> int:
    """全部已读。返回受影响行数。"""
    filters = _user_filters(user_id, site_group_id)
    filters.append(Notification.is_read == False)  # noqa: E712
    result = await db.execute(select(Notification).where(*filters))
    rows = result.scalars().all()
    now = datetime.now(timezone.utc)
    for n in rows:
        n.is_read = True
        n.read_at = now
    await db.flush()
    return len(rows)


async def delete_notification(
    db: AsyncSession, notification_id: int, user_id: int
) -> None:
    """删除单条站内信（校验归属）。"""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        raise NotFoundError("站内信不存在")
    await db.delete(notif)
    await db.flush()


# ──────────────────────────────────────────────
# Admin 视角（管理后台用）
# ──────────────────────────────────────────────


async def admin_list_notifications(
    db: AsyncSession,
    *,
    site_group_id: int | None = None,
    type: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Notification]:
    """管理后台列表：按站点组查询所有用户的通知，预加载 user 关系。

    支持按 type / user_id 过滤。返回结果按 created_at 倒序。
    """
    from app.models.user import User
    from sqlalchemy.orm import selectinload

    filters = []
    if site_group_id:
        filters.append(
            (Notification.site_group_id == site_group_id)
            | (Notification.site_group_id.is_(None))
        )
    if type and type != "all":
        filters.append(Notification.type == type)
    if user_id:
        filters.append(Notification.user_id == user_id)

    result = await db.execute(
        select(Notification)
        .options(selectinload(Notification.user))
        .where(*filters)
        .order_by(Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def search_users_for_push(
    db: AsyncSession,
    *,
    keyword: str,
    site_group_id: int | None = None,
    limit: int = 10,
) -> list:
    """用户搜索（用于站内信推送目标选择）。

    User 为全局模型（无 site_group_id），不按租户过滤，与积分模块用户搜索一致。
    返回 User 列表（仅 id / username / email 字段在模板中使用）。
    """
    from app.models.user import User

    filters = [User.is_active == True]  # noqa: E712
    if keyword:
        filters.append(User.username.ilike(f"%{keyword}%"))

    result = await db.execute(
        select(User).where(*filters).order_by(User.username).limit(limit)
    )
    return list(result.scalars().all())


async def get_site_user_ids(
    db: AsyncSession, *, site_group_id: int | None = None
) -> list[int]:
    """查询所有启用用户的 ID（用于"全体用户"广播）。

    User 为全局模型，无站点隔离；但站内信记录写入时会带 site_group_id，
    因此广播后通知仍归属于当前租户。
    """
    from app.models.user import User

    filters = [User.is_active == True]  # noqa: E712
    result = await db.execute(select(User.id).where(*filters))
    return [int(r) for r in result.scalars().all()]
