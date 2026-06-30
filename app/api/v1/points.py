"""积分系统 API。

路由分组：

* ``GET    /points/methods``                  —— 列出可用检测方式（管理员配置任务用）
* ``GET    /points/tasks``                    —— 管理员列出积分任务
* ``POST   /points/tasks``                    —— 管理员创建积分任务
* ``GET    /points/tasks/{id}``               —— 管理员获取任务详情
* ``PUT    /points/tasks/{id}``               —— 管理员更新任务
* ``DELETE /points/tasks/{id}``               —— 管理员删除任务
* ``GET    /points/records``                  —— 管理员查询全部积分明细
* ``GET    /points/records/mine``             —— 用户查询自己的积分明细
* ``POST   /points/admin/award``              —— 管理员手动发放/扣减积分
* ``GET    /points/balance``                 —— 用户查询自己的积分余额
* ``POST   /points/tasks/{id}/complete``      —— 用户完成主动型任务（如每日签到）
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user, require_staff
from app.core.db import get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.points import PointRecord, PointTask
from app.points import schemas
from app.points.registry import point_detector_registry
from app.points.service import (
    award_points,
    complete_task,
    get_balance,
)
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/points", tags=["points"])


# ──────────────────────────────────────────────
# 站点组过滤辅助
# ──────────────────────────────────────────────


def _apply_tenant_filter(query, model, tenant: TenantContext, user: CurrentUser):
    """非超级用户按站点组过滤。"""
    if tenant.site_group_id and not user.is_superuser:
        return query.where(
            (model.site_group_id == tenant.site_group_id)
            | (model.site_group_id.is_(None))
        )
    return query


# ──────────────────────────────────────────────
# 检测方式
# ──────────────────────────────────────────────


@router.get("/methods", response_model=list[schemas.DetectorMethodOut])
async def list_detector_methods(
    user=Depends(require_staff),
):
    """列出已注册的积分检测方式（含内置与插件注入）。"""
    return point_detector_registry.list_metadata()


# ──────────────────────────────────────────────
# 积分任务（管理员）
# ──────────────────────────────────────────────


@router.get("/tasks", response_model=list[schemas.PointTaskOut])
async def list_tasks(
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """管理员列出积分任务。"""
    query = select(PointTask).order_by(PointTask.id.desc())
    query = _apply_tenant_filter(query, PointTask, tenant, user)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/tasks", response_model=schemas.PointTaskOut, status_code=201)
async def create_task(
    body: schemas.PointTaskCreate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """创建积分任务。

    ``detection_method`` 必须为已注册的检测方式之一。
    """
    if point_detector_registry.get(body.detection_method) is None:
        raise NotFoundError(f"检测方式 {body.detection_method} 未注册")

    task = PointTask(
        name=body.name,
        description=body.description,
        detection_method=body.detection_method,
        points=body.points,
        is_active=body.is_active,
        config=body.config,
        site_group_id=tenant.site_group_id,
        created_by_id=user.id,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


@router.get("/tasks/{task_id}", response_model=schemas.PointTaskOut)
async def get_task(
    task_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """获取积分任务详情。"""
    query = select(PointTask).where(PointTask.id == task_id)
    query = _apply_tenant_filter(query, PointTask, tenant, user)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("积分任务不存在")
    return task


@router.put("/tasks/{task_id}", response_model=schemas.PointTaskOut)
async def update_task(
    task_id: int,
    body: schemas.PointTaskUpdate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """更新积分任务。"""
    query = select(PointTask).where(PointTask.id == task_id)
    query = _apply_tenant_filter(query, PointTask, tenant, user)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("积分任务不存在")

    update_data = body.model_dump(exclude_unset=True)
    if (
        "detection_method" in update_data
        and update_data["detection_method"] is not None
        and point_detector_registry.get(update_data["detection_method"]) is None
    ):
        raise NotFoundError(
            f"检测方式 {update_data['detection_method']} 未注册"
        )

    for key, value in update_data.items():
        setattr(task, key, value)

    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """删除积分任务。"""
    query = select(PointTask).where(PointTask.id == task_id)
    query = _apply_tenant_filter(query, PointTask, tenant, user)
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("积分任务不存在")
    await db.delete(task)
    await db.commit()
    return {"success": True}


# ──────────────────────────────────────────────
# 积分明细
# ──────────────────────────────────────────────


def _record_out(r: PointRecord) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "delta": r.delta,
        "balance_after": r.balance_after,
        "source": r.source,
        "task_id": r.task_id,
        "ref_type": r.ref_type,
        "ref_id": r.ref_id,
        "description": r.description,
        "site_group_id": r.site_group_id,
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


@router.get("/records", response_model=list[schemas.PointRecordOut])
async def list_records(
    user_id: int | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """管理员查询全部积分明细。"""
    query = select(PointRecord).order_by(PointRecord.id.desc())
    query = _apply_tenant_filter(query, PointRecord, tenant, user)
    if user_id is not None:
        query = query.where(PointRecord.user_id == user_id)
    if source:
        query = query.where(PointRecord.source == source)
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return [_record_out(r) for r in result.scalars().all()]


@router.get("/records/mine", response_model=list[schemas.PointRecordOut])
async def list_my_records(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """用户查询自己的积分明细。"""
    query = (
        select(PointRecord)
        .where(PointRecord.user_id == user.id)
        .order_by(PointRecord.id.desc())
    )
    if tenant.site_group_id:
        query = query.where(
            (PointRecord.site_group_id == tenant.site_group_id)
            | (PointRecord.site_group_id.is_(None))
        )
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return [_record_out(r) for r in result.scalars().all()]


# ──────────────────────────────────────────────
# 余额
# ──────────────────────────────────────────────


@router.get("/balance", response_model=schemas.UserPointsOut)
async def get_my_balance(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """查询当前用户在当前租户下的积分余额。"""
    balance = await get_balance(db, user.id, tenant.site_group_id)
    return {
        "user_id": user.id,
        "site_group_id": tenant.site_group_id,
        "balance": balance,
    }


# ──────────────────────────────────────────────
# 任务完成（用户主动）
# ──────────────────────────────────────────────


@router.post("/tasks/{task_id}/complete", response_model=schemas.PointRecordOut)
async def complete_my_task(
    task_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """完成主动型积分任务（如每日签到）。"""
    record = await complete_task(
        db,
        task_id=task_id,
        user_id=user.id,
        site_group_id=tenant.site_group_id,
    )
    await db.commit()
    await db.refresh(record)
    return _record_out(record)


# ──────────────────────────────────────────────
# 管理员手动发放/扣减
# ──────────────────────────────────────────────


@router.post("/admin/award", response_model=schemas.PointRecordOut)
async def admin_award(
    body: schemas.AdminAwardRequest,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """管理员手动发放或扣减指定用户的积分。

    ``delta`` 为正则发放，为负则扣减（余额不足时拒绝）。
    """
    if body.delta == 0:
        raise ForbiddenError("积分变动数额不能为 0")

    if body.delta > 0:
        record = await award_points(
            db,
            body.user_id,
            body.delta,
            source="admin",
            site_group_id=tenant.site_group_id,
            description=body.description or f"管理员 {user.username} 手动发放",
        )
    else:
        # 扣减走 deduct_points 以做余额校验
        from app.points.service import deduct_points

        record = await deduct_points(
            db,
            body.user_id,
            -body.delta,
            site_group_id=tenant.site_group_id,
            description=body.description or f"管理员 {user.username} 手动扣减",
        )
    await db.commit()
    await db.refresh(record)
    return _record_out(record)
