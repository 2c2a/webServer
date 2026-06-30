"""工单 API。"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, get_current_user, require_staff
from app.core.db import get_db
from app.core.exceptions import ForbiddenError, NotFoundError
from app.models.ticket import Ticket, TicketCategory, TicketComment
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketCreate(BaseModel):
    title: str
    description: str
    category_id: int | None = None
    priority: str = "normal"


class TicketUpdate(BaseModel):
    status: str | None = None
    priority: str | None = None
    assignee_id: int | None = None


class TicketCommentCreate(BaseModel):
    content: str
    is_internal: bool = False


class TicketCommentOut(BaseModel):
    id: int
    author_id: int
    content: str
    is_internal: bool
    created_at: str

    model_config = {"from_attributes": True}


class TicketOut(BaseModel):
    id: int
    ticket_no: str
    title: str
    description: str
    status: str
    priority: str
    category_id: int | None
    creator_id: int
    assignee_id: int | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TicketDetailOut(TicketOut):
    comments: list[TicketCommentOut]


class TicketCategoryOut(BaseModel):
    id: int
    name: str
    description: str | None
    default_priority: str

    model_config = {"from_attributes": True}


def _ticket_out(t: Ticket) -> dict:
    return {
        "id": t.id,
        "ticket_no": t.ticket_no,
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "category_id": t.category_id,
        "creator_id": t.creator_id,
        "assignee_id": t.assignee_id,
        "created_at": t.created_at.isoformat() if t.created_at else "",
        "updated_at": t.updated_at.isoformat() if t.updated_at else "",
    }


@router.get("/categories", response_model=list[TicketCategoryOut])
async def list_ticket_categories(
    db: AsyncSession = Depends(get_db),
):
    """列出启用的工单分类。"""
    result = await db.execute(
        select(TicketCategory)
        .where(TicketCategory.is_active == True)  # noqa: E712
        .order_by(TicketCategory.display_order, TicketCategory.id)
    )
    return result.scalars().all()


@router.get("/mine", response_model=list[TicketOut])
async def list_my_tickets(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出我的工单。"""
    result = await db.execute(
        select(Ticket)
        .where(Ticket.creator_id == user.id)
        .order_by(Ticket.created_at.desc())
    )
    tickets = result.scalars().all()
    return [_ticket_out(t) for t in tickets]


@router.get("/all", response_model=list[TicketOut])
async def list_all_tickets(
    status: str | None = None,
    assignee_id: int | None = None,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """后台列出所有工单。"""
    query = select(Ticket).order_by(Ticket.created_at.desc())
    if tenant.site_group_id:
        query = query.where(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    if status:
        query = query.where(Ticket.status == status)
    if assignee_id is not None:
        query = query.where(Ticket.assignee_id == assignee_id)
    result = await db.execute(query)
    tickets = result.scalars().all()
    return [_ticket_out(t) for t in tickets]


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket(
    ticket_id: int,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取工单详情。普通用户只能看自己的，staff 可查看所有。"""
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.comments).selectinload(TicketComment.author))
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单不存在")
    if ticket.creator_id != user.id and not (user.is_staff or user.is_superuser):
        raise ForbiddenError("无权查看该工单")

    comments = [
        {
            "id": c.id,
            "author_id": c.author_id,
            "content": c.content,
            "is_internal": c.is_internal,
            "created_at": c.created_at.isoformat() if c.created_at else "",
        }
        for c in ticket.comments
        if not c.is_internal or (user.is_staff or user.is_superuser)
    ]

    data = _ticket_out(ticket)
    data["comments"] = comments
    return data


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建工单。"""
    if body.category_id is not None:
        cat_result = await db.execute(
            select(TicketCategory).where(
                TicketCategory.id == body.category_id,
                TicketCategory.is_active == True,  # noqa: E712
            )
        )
        if cat_result.scalar_one_or_none() is None:
            raise NotFoundError("工单分类不存在")

    ticket = Ticket(
        ticket_no=f"TK-{uuid.uuid4().hex[:8].upper()}",
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        priority=body.priority,
        status="open",
        source="web",
        creator_id=user.id,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    # 触发工单提交积分事件（被动检测器，失败不影响工单创建）
    try:
        from app.points.service import trigger_passive_event

        await trigger_passive_event(
            db,
            method_id="ticket_submit",
            user_id=user.id,
            site_group_id=user.site_group_id,
            extra={"ticket": ticket, "ref_type": "ticket", "ref_id": ticket.id},
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("工单提交积分触发失败 ticket_id=%s", ticket.id)

    return _ticket_out(ticket)


@router.put("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """更新工单状态/优先级/指派人（后台）。"""
    filters = [Ticket.id == ticket_id]
    if tenant.site_group_id:
        filters.append(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    result = await db.execute(select(Ticket).where(*filters))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单不存在")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ticket, key, value)

    await db.commit()
    await db.refresh(ticket)
    return _ticket_out(ticket)


@router.post("/{ticket_id}/comments", response_model=TicketCommentOut, status_code=201)
async def add_comment(
    ticket_id: int,
    body: TicketCommentCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """添加工单评论。"""
    filters = [Ticket.id == ticket_id]
    if tenant.site_group_id:
        filters.append(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    result = await db.execute(select(Ticket).where(*filters))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单不存在")

    if ticket.creator_id != user.id and not (user.is_staff or user.is_superuser):
        raise ForbiddenError("无权评论该工单")

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=user.id,
        content=body.content,
        is_internal=body.is_internal if (user.is_staff or user.is_superuser) else False,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return {
        "id": comment.id,
        "author_id": comment.author_id,
        "content": comment.content,
        "is_internal": comment.is_internal,
        "created_at": comment.created_at.isoformat() if comment.created_at else "",
    }
