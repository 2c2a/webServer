"""积分服务：余额维护、流水写入、任务完成与被动事件触发。

所有积分变动必须通过此模块，保证余额与流水的一致性（同一事务内更新
``UserPoints.balance`` 与写入 ``PointRecord``）。

主要入口：

* :func:`award_points`：发放积分（来源 task / admin / refund）。
* :func:`deduct_points`：扣除积分（来源 consume），余额不足抛
  :class:`ForbiddenError`。
* :func:`get_balance` / :func:`get_or_create_balance`：查询余额。
* :func:`complete_task`：主动型任务完成（如每日签到）。
* :func:`trigger_passive_event`：被动型事件触发（如工单创建）。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.points import PointRecord, PointTask, UserPoints
from app.points.detectors import DetectorContext
from app.points.registry import point_detector_registry

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 余额
# ──────────────────────────────────────────────


async def get_or_create_balance(
    db: AsyncSession, user_id: int, site_group_id: int | None
) -> UserPoints:
    """获取或创建用户在某站点组的积分余额记录。"""
    result = await db.execute(
        select(UserPoints).where(
            UserPoints.user_id == user_id,
            UserPoints.site_group_id.is_(site_group_id)
            if site_group_id is None
            else UserPoints.site_group_id == site_group_id,
        )
    )
    balance = result.scalar_one_or_none()
    if balance is None:
        balance = UserPoints(
            user_id=user_id, site_group_id=site_group_id, balance=0
        )
        db.add(balance)
        await db.flush()
    return balance


async def get_balance(
    db: AsyncSession, user_id: int, site_group_id: int | None
) -> int:
    """查询用户在某站点组的积分余额（无记录视为 0）。"""
    result = await db.execute(
        select(UserPoints.balance).where(
            UserPoints.user_id == user_id,
            UserPoints.site_group_id.is_(site_group_id)
            if site_group_id is None
            else UserPoints.site_group_id == site_group_id,
        )
    )
    bal = result.scalar_one_or_none()
    return int(bal) if bal is not None else 0


# ──────────────────────────────────────────────
# 流水写入
# ──────────────────────────────────────────────


async def award_points(
    db: AsyncSession,
    user_id: int,
    delta: int,
    *,
    source: str,
    site_group_id: int | None,
    task_id: int | None = None,
    ref_type: str | None = None,
    ref_id: int | None = None,
    description: str | None = None,
) -> PointRecord:
    """发放积分（delta 可为正可为负），更新余额并写入流水。

    对于扣分场景请优先使用 :func:`deduct_points`（含余额校验）。
    """
    if delta == 0:
        raise ValueError("积分变动数额不能为 0")

    balance = await get_or_create_balance(db, user_id, site_group_id)
    new_balance = balance.balance + delta
    balance.balance = new_balance

    record = PointRecord(
        user_id=user_id,
        delta=delta,
        balance_after=new_balance,
        source=source,
        task_id=task_id,
        ref_type=ref_type,
        ref_id=ref_id,
        description=description,
        site_group_id=site_group_id,
    )
    db.add(record)
    await db.flush()
    return record


async def deduct_points(
    db: AsyncSession,
    user_id: int,
    amount: int,
    *,
    site_group_id: int | None,
    ref_type: str | None = None,
    ref_id: int | None = None,
    description: str | None = None,
) -> PointRecord:
    """扣除积分。余额不足抛 :class:`ForbiddenError`。"""
    if amount <= 0:
        raise ValueError("扣除数额必须为正")
    balance = await get_or_create_balance(db, user_id, site_group_id)
    if balance.balance < amount:
        raise ForbiddenError("积分余额不足")
    return await award_points(
        db,
        user_id,
        -amount,
        source="consume",
        site_group_id=site_group_id,
        ref_type=ref_type,
        ref_id=ref_id,
        description=description,
    )


# ──────────────────────────────────────────────
# 任务完成
# ──────────────────────────────────────────────


async def _load_active_task(
    db: AsyncSession, task_id: int, site_group_id: int | None
) -> PointTask:
    """加载并校验任务存在且启用，按租户过滤。"""
    result = await db.execute(select(PointTask).where(PointTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("积分任务不存在")
    if not task.is_active:
        raise NotFoundError("积分任务已停用")
    # 租户隔离：任务归属站点组必须匹配（或为全局任务）
    if site_group_id is not None and task.site_group_id not in (None, site_group_id):
        raise NotFoundError("积分任务不存在")
    return task


async def complete_task(
    db: AsyncSession,
    *,
    task_id: int,
    user_id: int,
    site_group_id: int | None,
    extra: dict | None = None,
) -> PointRecord:
    """完成主动型积分任务。

    查找任务对应的检测器，调用 ``is_completable`` 与 ``complete``，
    通过后发放积分并写入流水。
    """
    task = await _load_active_task(db, task_id, site_group_id)

    detector = point_detector_registry.get(task.detection_method)
    if detector is None:
        raise NotFoundError(
            f"检测方式 {task.detection_method} 未注册"
        )
    if detector.passive:
        raise ForbiddenError("该任务为被动触发，不可主动完成")

    ctx = DetectorContext(
        user_id=user_id,
        task=task,
        site_group_id=site_group_id,
        db=db,
        extra=extra,
    )
    if not await detector.is_completable(ctx):
        raise ForbiddenError("当前不可完成该任务")
    if not await detector.complete(ctx):
        raise ForbiddenError("任务完成失败（可能已完成）")

    return await award_points(
        db,
        user_id,
        task.points,
        source="task",
        site_group_id=site_group_id,
        task_id=task.id,
        description=f"完成任务：{task.name}",
    )


async def trigger_passive_event(
    db: AsyncSession,
    *,
    method_id: str,
    user_id: int,
    site_group_id: int | None,
    extra: dict | None = None,
) -> list[PointRecord]:
    """触发被动型积分事件。

    遍历匹配检测方式且归属当前租户的启用任务，对每个任务调用检测器
    ``complete``，通过则发放积分。返回成功发放的流水列表。
    """
    detector = point_detector_registry.get(method_id)
    if detector is None or not detector.passive:
        return []

    # 查询当前租户下所有匹配检测方式的启用任务
    query = select(PointTask).where(
        PointTask.detection_method == method_id,
        PointTask.is_active == True,  # noqa: E712
    )
    if site_group_id is not None:
        query = query.where(
            (PointTask.site_group_id == site_group_id)
            | (PointTask.site_group_id.is_(None))
        )
    result = await db.execute(query)
    tasks = result.scalars().all()

    records: list[PointRecord] = []
    for task in tasks:
        ctx = DetectorContext(
            user_id=user_id,
            task=task,
            site_group_id=site_group_id,
            db=db,
            extra=extra,
        )
        try:
            ok = await detector.complete(ctx)
        except Exception:  # noqa: BLE001
            logger.exception(
                "被动检测器 %s 处理任务 %s 时出错",
                method_id,
                task.id,
            )
            continue
        if not ok:
            continue
        record = await award_points(
            db,
            user_id,
            task.points,
            source="task",
            site_group_id=site_group_id,
            task_id=task.id,
            ref_type=extra.get("ref_type") if extra else None,
            ref_id=extra.get("ref_id") if extra else None,
            description=f"完成任务：{task.name}",
        )
        records.append(record)
    return records
