"""云电脑用户 API。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.db import get_db
from app.models.operations import CloudComputerUser
from app.security.field_cipher import decrypt_field

router = APIRouter(prefix="/cloud-computers", tags=["cloud-computers"])


class CloudComputerOut(BaseModel):
    id: int
    username: str
    fullname: str | None
    status: str
    product_id: int

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CloudComputerOut])
async def list_my_cloud_computers(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出我的云电脑。"""
    result = await db.execute(
        select(CloudComputerUser)
        .where(CloudComputerUser.owner_id == user.id)
        .order_by(CloudComputerUser.created_at.desc())
    )
    users = result.scalars().all()
    return [
        CloudComputerOut(id=u.id, username=u.username, fullname=u.fullname, status=u.status, product_id=u.product_id)
        for u in users
    ]


@router.get("/{ccu_id}/password")
async def get_initial_password(
    ccu_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取初始密码（阅后即焚：查看后清除）。"""
    result = await db.execute(select(CloudComputerUser).where(CloudComputerUser.id == ccu_id))
    ccu = result.scalar_one_or_none()
    if ccu is None or ccu.owner_id != user.id:
        return {"error": "不存在"}

    if ccu.password_viewed or not ccu.initial_password_cipher:
        return {"error": "密码已查看或不存在"}

    password = decrypt_field(ccu.initial_password_cipher, "cloud_computer_user.initial_password")
    # 阅后即焚
    ccu.password_viewed = True
    ccu.password_viewed_at = datetime.now(timezone.utc)
    ccu.initial_password_cipher = None
    await db.commit()

    return {"password": password}
