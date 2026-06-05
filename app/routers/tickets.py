"""
工单系统 CRUD 路由

包含工单创建、查询、更新、评论及工单页面
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession, PaginationParams
from app.models.ticket import Ticket, TicketComment
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.ticket import (
    TicketCommentCreate,
    TicketCommentResponse,
    TicketCreate,
    TicketResponse,
    TicketUpdate,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# ========== 工单 API ==========


@router.get(
    "/api/tickets",
    response_model=APIResponse[PaginatedResponse[TicketResponse]],
    tags=["tickets"],
)
async def list_tickets(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """列出工单"""
    count_stmt = select(func.count()).select_from(Ticket)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Ticket)
        .order_by(Ticket.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    tickets = result.scalars().all()

    items = [TicketResponse.model_validate(t) for t in tickets]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/api/tickets",
    response_model=APIResponse[TicketResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
)
async def create_ticket(
    body: TicketCreate,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """创建工单"""
    ticket = Ticket(
        id=str(uuid4()),
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        priority=body.priority,
        related_product_id=body.related_product_id,
        related_host_id=body.related_host_id,
        creator_id=user.id,
    )
    db.add(ticket)
    await db.flush()
    return APIResponse(data=TicketResponse.model_validate(ticket), message="工单创建成功")


@router.get(
    "/api/tickets/{ticket_id}",
    response_model=APIResponse[TicketResponse],
    tags=["tickets"],
)
async def get_ticket(
    ticket_id: str,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """获取工单详情"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")
    return APIResponse(data=TicketResponse.model_validate(ticket))


@router.put(
    "/api/tickets/{ticket_id}",
    response_model=APIResponse[TicketResponse],
    tags=["tickets"],
)
async def update_ticket(
    ticket_id: str,
    body: TicketUpdate,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """更新工单"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(ticket, field, value)

    await db.flush()
    return APIResponse(data=TicketResponse.model_validate(ticket), message="工单更新成功")


@router.post(
    "/api/tickets/{ticket_id}/comments",
    response_model=APIResponse[TicketCommentResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["tickets"],
)
async def add_ticket_comment(
    ticket_id: str,
    body: TicketCommentCreate,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """添加工单评论"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    comment = TicketComment(
        id=str(uuid4()),
        ticket_id=ticket_id,
        author_id=user.id,
        content=body.content,
        is_internal=body.is_internal,
    )
    db.add(comment)
    await db.flush()
    return APIResponse(data=TicketCommentResponse.model_validate(comment), message="评论添加成功")


@router.put(
    "/api/tickets/{ticket_id}/status",
    response_model=APIResponse[TicketResponse],
    tags=["tickets"],
)
async def update_ticket_status(
    ticket_id: str,
    status_value: str,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """更新工单状态"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    valid_statuses = ["pending", "in_progress", "resolved", "closed", "reopened"]
    if status_value not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的状态值，允许: {', '.join(valid_statuses)}",
        )

    ticket.status = status_value
    await db.flush()
    return APIResponse(data=TicketResponse.model_validate(ticket), message="工单状态已更新")


# ========== 工单页面 ==========


@router.get("/tickets/", tags=["tickets-pages"])
async def tickets_page(
    request: Request,
    user: CurrentUser,
):
    """工单列表页面"""
    return templates.TemplateResponse("tickets/ticket_list.html", {
        "request": request,
        "user": user,
    })


@router.get("/tickets/{ticket_id}", tags=["tickets-pages"])
async def ticket_detail_page(
    request: Request,
    ticket_id: str,
    user: CurrentUser,
    db: DBSession,
):
    """工单详情页面"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="工单不存在")

    return templates.TemplateResponse("tickets/ticket_detail.html", {
        "request": request,
        "user": user,
        "ticket": ticket,
    })
