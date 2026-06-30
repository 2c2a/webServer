"""站内信事件触发器：供其他模块调用，发送业务通知。

被动触发失败不影响主流程：所有触发器内部捕获异常并记录日志，
不向上抛出，与积分被动检测器的容错策略一致。
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.notifications import service as notif_service
from app.notifications.types import NotificationLevel, NotificationType

logger = logging.getLogger(__name__)


async def _safe_create(db: AsyncSession, **kwargs) -> None:
    """安全创建：失败仅记录日志，不抛出。"""
    try:
        await notif_service.create_notification(db, **kwargs)
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("notification_create_failed kwargs=%s", kwargs)
        # 回滚可能污染会话，但调用方后续若使用同一会话需自行处理；
        # 这里仅记录，不强制 rollback，避免影响调用方事务。


async def notify_ticket_replied(
    db: AsyncSession,
    *,
    ticket_id: int,
    recipient_id: int,
    ticket_no: str,
    site_group_id: int | None,
) -> None:
    """工单有新回复。"""
    await _safe_create(
        db,
        user_id=recipient_id,
        type=NotificationType.TICKET,
        level=NotificationLevel.INFO,
        title="工单回复",
        content=f"您提交的工单 {ticket_no} 已有新回复",
        ref_type="ticket",
        ref_id=ticket_id,
        action_url=f"/tickets/{ticket_id}",
        site_group_id=site_group_id,
    )


async def notify_ticket_status_changed(
    db: AsyncSession,
    *,
    ticket_id: int,
    recipient_id: int,
    ticket_no: str,
    new_status: str,
    site_group_id: int | None,
) -> None:
    """工单状态变更。"""
    status_label = {
        "open": "待处理",
        "pending": "待处理",
        "in_progress": "处理中",
        "resolved": "已解决",
        "closed": "已关闭",
    }.get(new_status, new_status)
    await _safe_create(
        db,
        user_id=recipient_id,
        type=NotificationType.TICKET,
        level=NotificationLevel.SUCCESS,
        title="工单状态",
        content=f"工单 {ticket_no} 已被标记为 {status_label}",
        ref_type="ticket",
        ref_id=ticket_id,
        action_url=f"/tickets/{ticket_id}",
        site_group_id=site_group_id,
    )


async def notify_points_received(
    db: AsyncSession,
    *,
    user_id: int,
    delta: int,
    balance: int,
    source: str,
    site_group_id: int | None,
) -> None:
    """积分到账。"""
    sign = "+" if delta >= 0 else ""
    await _safe_create(
        db,
        user_id=user_id,
        type=NotificationType.POINTS,
        level=NotificationLevel.BRAND,
        title="积分到账",
        content=f"获得 {sign}{delta} 积分，当前余额 {balance}",
        ref_type="point_record",
        ref_id=None,
        site_group_id=site_group_id,
    )


async def notify_password_changed(
    db: AsyncSession, *, user_id: int, site_group_id: int | None
) -> None:
    """账户安全：密码已修改。"""
    await _safe_create(
        db,
        user_id=user_id,
        type=NotificationType.SECURITY,
        level=NotificationLevel.SUCCESS,
        title="账户安全",
        content="您的密码已成功修改",
        site_group_id=site_group_id,
    )


async def notify_product_published(
    db: AsyncSession,
    *,
    product_id: int,
    product_name: str,
    recipient_ids: list[int],
    site_group_id: int | None,
) -> None:
    """产品上架（广播给指定用户列表）。"""
    for uid in recipient_ids:
        await _safe_create(
            db,
            user_id=uid,
            type=NotificationType.PRODUCT,
            level=NotificationLevel.BRAND,
            title="产品上架",
            content=f"新产品 {product_name} 已上架",
            ref_type="product",
            ref_id=product_id,
            action_url="/cloud-computers",
            site_group_id=site_group_id,
        )


async def notify_maintenance(
    db: AsyncSession,
    *,
    title: str,
    content: str,
    recipient_ids: list[int],
    site_group_id: int | None,
) -> None:
    """维护通知（广播）。"""
    for uid in recipient_ids:
        await _safe_create(
            db,
            user_id=uid,
            type=NotificationType.MAINTENANCE,
            level=NotificationLevel.WARNING,
            title=title,
            content=content,
            site_group_id=site_group_id,
        )
