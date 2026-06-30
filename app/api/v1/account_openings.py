"""开户申请 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.db import get_db
from app.models.operations import AccountOpeningRequest
from app.tasks.operations import process_account_opening

router = APIRouter(prefix="/account-openings", tags=["account-openings"])


class AccountOpeningCreate(BaseModel):
    target_product_id: int
    username: str
    user_fullname: str | None = None
    user_email: str | None = None
    user_description: str | None = None
    contact_email: str
    contact_phone: str | None = None
    requested_disk_capacity: dict | None = None


class AccountOpeningOut(BaseModel):
    id: int
    status: str
    username: str
    target_product_id: int

    model_config = {"from_attributes": True}


@router.get("", response_model=list[AccountOpeningOut])
async def list_my_account_openings(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出我的开户申请。"""
    result = await db.execute(
        select(AccountOpeningRequest)
        .where(AccountOpeningRequest.applicant_id == user.id)
        .order_by(AccountOpeningRequest.created_at.desc())
    )
    reqs = result.scalars().all()
    return [
        AccountOpeningOut(id=r.id, status=r.status, username=r.username, target_product_id=r.target_product_id)
        for r in reqs
    ]


@router.post("", response_model=AccountOpeningOut, status_code=201)
async def create_account_opening(
    body: AccountOpeningCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交开户申请（异步处理，不阻塞前端）。

    提交后立即返回 pending 状态，后台通过 RedisHuey 任务执行 WinRM 操作。
    """
    req = AccountOpeningRequest(
        applicant_id=user.id,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        username=body.username,
        user_fullname=body.user_fullname,
        user_email=body.user_email,
        user_description=body.user_description,
        target_product_id=body.target_product_id,
        requested_disk_capacity=body.requested_disk_capacity,
        status="pending",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    # 异步任务处理（不阻塞响应）
    process_account_opening.schedule(args=(req.id,))

    return AccountOpeningOut(
        id=req.id, status=req.status, username=req.username, target_product_id=req.target_product_id
    )
