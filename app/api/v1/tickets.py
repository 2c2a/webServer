"""工单 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.db import get_db
from app.models.ticket import Ticket

router = APIRouter(prefix="/tickets", tags=["tickets"])


class TicketCreate(BaseModel):
    title: str
    description: str
    category_id: int | None = None
    priority: str = "normal"


class TicketOut(BaseModel):
    id: int
    ticket_no: str
    title: str
    status: str
    priority: str


@router.get("", response_model=list[TicketOut])
async def list_tickets(
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
    return [
        TicketOut(id=t.id, ticket_no=t.ticket_no, title=t.title, status=t.status, priority=t.priority)
        for t in tickets
    ]


@router.post("", response_model=TicketOut, status_code=201)
async def create_ticket(
    body: TicketCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建工单。"""
    import uuid

    ticket = Ticket(
        ticket_no=f"TK-{uuid.uuid4().hex[:8].upper()}",
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        priority=body.priority,
        status="open",
        creator_id=user.id,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return TicketOut(
        id=ticket.id, ticket_no=ticket.ticket_no, title=ticket.title,
        status=ticket.status, priority=ticket.priority,
    )
