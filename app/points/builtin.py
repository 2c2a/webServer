"""内置积分检测器。

* :class:`DailyCheckinDetector`（``daily_checkin``）：每日签到，主动触发。
  通过查询当天是否已存在该任务的积分流水判断是否可完成。
* :class:`TicketSubmitDetector`（``ticket_submit``）：工单提交，被动触发。
  系统在创建工单后调用，按 ``config.category_id`` 过滤是否计积分。

第三方插件可参照此类实现自定义检测器并注册到
:data:`app.points.registry.point_detector_registry`。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.points import PointRecord
from app.points.detectors import DetectorContext, PointTaskDetector


def _utc_today_range() -> tuple[datetime, datetime]:
    """返回今天的 UTC 起止时间（[00:00, 次日 00:00)）。"""
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


class DailyCheckinDetector(PointTaskDetector):
    """每日签到检测器。

    每个用户每天每个签到任务只能完成一次。完成状态通过查询
    ``point_record`` 中当天的 ``task`` 流水判定，无需额外签到表。
    """

    method_id = "daily_checkin"
    name = "每日签到"
    description = "用户每日主动签到一次获得积分，每天仅可完成一次。"
    passive = False

    async def _has_checked_in_today(
        self, db: AsyncSession, user_id: int, task_id: int
    ) -> bool:
        start, end = _utc_today_range()
        result = await db.execute(
            select(PointRecord.id)
            .where(
                PointRecord.user_id == user_id,
                PointRecord.task_id == task_id,
                PointRecord.source == "task",
                PointRecord.created_at >= start,
                PointRecord.created_at < end,
            )
            .limit(1)
        )
        return result.first() is not None

    async def is_completable(self, ctx: DetectorContext) -> bool:
        return not await self._has_checked_in_today(ctx.db, ctx.user_id, ctx.task.id)

    async def complete(self, ctx: DetectorContext) -> bool:
        # 复查一次，防止并发重复签到
        if await self._has_checked_in_today(ctx.db, ctx.user_id, ctx.task.id):
            return False
        # 实际积分发放由 service 统一处理，此处仅返回可完成
        return True


class TicketSubmitDetector(PointTaskDetector):
    """工单提交检测器。

    被动触发：工单创建后由系统调用 :meth:`trigger_on_ticket_created`，
    按 ``config.category_id``（可选）过滤后对匹配任务发放积分。

    任务配置 ``config`` 示例::

        {"category_id": 3}   # 仅 category_id=3 的工单计积分
        {}                    # 所有工单均计积分
    """

    method_id = "ticket_submit"
    name = "工单提交"
    description = "提交工单后获得积分，可配置仅特定分类的工单计积分。"
    passive = True

    async def is_completable(self, ctx: DetectorContext) -> bool:
        # 被动检测器不暴露给用户主动调用
        return False

    async def complete(self, ctx: DetectorContext) -> bool:
        # 由 trigger_on_ticket_created 调用，传入 extra={"ticket": ...}
        ticket: Any = (ctx.extra or {}).get("ticket")
        if ticket is None:
            return False
        cfg = ctx.task.config or {}
        required_category = cfg.get("category_id")
        if required_category is not None:
            ticket_category = getattr(ticket, "category_id", None)
            if ticket_category != required_category:
                return False
        return True


#: 内置检测器实例（单例）
daily_checkin_detector = DailyCheckinDetector()
ticket_submit_detector = TicketSubmitDetector()


def register_builtins() -> None:
    """注册全部内置检测器到全局注册表。"""
    from app.points.registry import point_detector_registry

    point_detector_registry.register(daily_checkin_detector)
    point_detector_registry.register(ticket_submit_detector)
