"""HTMX 动态片段路由（不可缓存、基于用户状态与租户依赖）。

策略（来自架构要求）：
- 用户导航、统计等动态内容由 HTMX 在页面加载后发起独立请求
- 服务端基于 Ed25519 验签和租户依赖实时返回不可缓存的 HTML 片段
- 片段响应标记 no-store，确保数据安全隔离
- 支持 HTMX OOB（Out of Band）swap
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, get_current_user_optional
from app.cache.fragments import fragment_response
from app.core.db import get_db
from app.models.announcement import Announcement
from app.models.host import Host
from app.models.operations import AccountOpeningRequest, CloudComputerUser, Product, ProductGroup
from app.models.points import PointRecord, PointTask, UserPoints
from app.models.tenant import SystemConfig
from app.models.ticket import Ticket, TicketCategory, TicketComment
from app.points import service as points_service
from app.points.detectors import DetectorContext
from app.points.registry import point_detector_registry
from app.templates import render_template
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/fragments", tags=["fragments"])


@router.get("/nav")
async def nav_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """导航片段（基于用户状态，不可缓存）。"""
    cfg = {}
    try:
        from app.tenant.resolver import get_effective_config

        cfg = await get_effective_config(db, tenant)
    except Exception:  # noqa: BLE001
        pass

    html = await render_template(
        "nav.html",
        user=user,
        enable_registration=cfg.get("enable_registration", False),
    )
    return fragment_response(html, request=request)


@router.get("/stats")
async def stats_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """统计片段（基于用户权限，不可缓存）。

    普通用户看自己的统计，管理员看全局/租户统计。
    """
    if user is None:
        return fragment_response("<div></div>", request=request)

    # 站点隔离过滤
    sg_filter = []
    if tenant.site_group_id and not user.is_superuser:
        sg_filter = [Host.site_group_id == tenant.site_group_id]

    hosts_count = 0
    cloud_users_count = 0
    pending_tickets = 0
    pending_requests = 0

    try:
        if user.is_staff or user.is_superuser:
            hosts_result = await db.execute(
                select(func.count(Host.id)).where(*sg_filter)
            )
            hosts_count = hosts_result.scalar() or 0
        else:
            hosts_count = 0

        # 云电脑用户数
        cc_filter = []
        if not (user.is_staff or user.is_superuser):
            cc_filter = [CloudComputerUser.owner_id == user.id]
        cc_result = await db.execute(
            select(func.count(CloudComputerUser.id)).where(*cc_filter)
        )
        cloud_users_count = cc_result.scalar() or 0

        # 待处理工单
        ticket_filter = [Ticket.status.in_(["open", "pending", "processing"])]
        if not (user.is_staff or user.is_superuser):
            ticket_filter.append(Ticket.creator_id == user.id)
        ticket_result = await db.execute(
            select(func.count(Ticket.id)).where(*ticket_filter)
        )
        pending_tickets = ticket_result.scalar() or 0

        # 待处理开户申请
        req_filter = [AccountOpeningRequest.status == "pending"]
        if not (user.is_staff or user.is_superuser):
            req_filter.append(AccountOpeningRequest.applicant_id == user.id)
        req_result = await db.execute(
            select(func.count(AccountOpeningRequest.id)).where(*req_filter)
        )
        pending_requests = req_result.scalar() or 0
    except Exception:  # noqa: BLE001
        pass

    html = await render_template(
        "stats.html",
        stats={
            "hosts_count": hosts_count,
            "cloud_users_count": cloud_users_count,
            "pending_tickets": pending_tickets,
            "pending_requests": pending_requests,
        },
    )
    return fragment_response(html, request=request)


@router.get("/product-groups")
async def product_groups_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """产品组片段（基于租户隔离与可见性，不可缓存）。"""
    # 站点隔离 + 仅公开可见
    filters = [ProductGroup.is_active == True, ProductGroup.visibility == "public"]  # noqa: E712
    if tenant.site_group_id:
        filters.append(
            (ProductGroup.site_group_id == tenant.site_group_id)
            | (ProductGroup.site_group_id.is_(None))
        )

    result = await db.execute(
        select(ProductGroup)
        .where(*filters)
        .order_by(ProductGroup.display_order)
    )
    groups = result.scalars().all()

    # 加载每组的产品
    product_groups = []
    for pg in groups:
        prod_result = await db.execute(
            select(Product)
            .where(
                Product.product_group_id == pg.id,
                Product.is_available == True,  # noqa: E712
            )
            .order_by(Product.id)
        )
        products = prod_result.scalars().all()
        product_groups.append({"name": pg.name, "description": pg.description, "products": products})

    html = await render_template("product_groups.html", product_groups=product_groups)
    return fragment_response(html, request=request)


@router.get("/cloud-computers")
async def cloud_computers_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """云电脑产品列表片段（展示可申请的产品，基于租户，不可缓存）。

    设计稿显示的是"产品卡片"列表，用户点击"申请开通"跳转申请页。
    仅展示 is_available=True 且 visibility='public' 的产品，按 site_group_id 过滤。
    """
    query = (
        select(Product)
        .where(Product.is_available == True)  # noqa: E712
        .where(Product.visibility == "public")
        .order_by(Product.id.desc())
    )
    if tenant.site_group_id:
        query = query.where(
            (Product.site_group_id == tenant.site_group_id)
            | (Product.site_group_id.is_(None))
        )
    result = await db.execute(query)
    products = result.scalars().all()

    html = await render_template("cloud_computers_list.html", products=products)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 工单
# ──────────────────────────────────────────────


@router.get("/tickets/list")
async def tickets_list_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """我的工单列表片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    result = await db.execute(
        select(Ticket)
        .where(Ticket.creator_id == user.id)
        .order_by(Ticket.created_at.desc())
    )
    tickets = result.scalars().all()
    html = await render_template("tickets/list.html", tickets=tickets)
    return fragment_response(html, request=request)


@router.get("/tickets/form")
async def tickets_form_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """新建工单表单片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    result = await db.execute(
        select(TicketCategory)
        .where(TicketCategory.is_active == True)  # noqa: E712
        .order_by(TicketCategory.display_order, TicketCategory.id)
    )
    categories = result.scalars().all()
    html = await render_template("tickets/form.html", categories=categories)
    return fragment_response(html, request=request)


@router.post("/tickets/create")
async def tickets_create_fragment(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    category_id: str = Form(""),
    priority: str = Form("normal"),
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """提交新建工单表单，返回工单列表片段。

    避免直接 POST 到 REST API（/api/v1/tickets），后者要求 JSON body，
    而 HTML 表单默认提交 application/x-www-form-urlencoded。
    """
    import uuid

    if user is None:
        return fragment_response("<div>请先登录</div>", request=request)

    # 表单的 "未分类" 选项提交空字符串，需手动转换为 None
    cat_id: int | None = None
    if category_id.strip():
        try:
            cat_id = int(category_id)
        except ValueError:
            from app.core.exceptions import AppError
            raise AppError("分类 ID 无效") from None

    if cat_id is not None:
        cat_result = await db.execute(
            select(TicketCategory).where(
                TicketCategory.id == cat_id,
                TicketCategory.is_active == True,  # noqa: E712
            )
        )
        if cat_result.scalar_one_or_none() is None:
            from app.core.exceptions import NotFoundError
            raise NotFoundError("工单分类不存在")

    ticket = Ticket(
        ticket_no=f"TK-{uuid.uuid4().hex[:8].upper()}",
        title=title,
        description=description,
        category_id=cat_id,
        priority=priority,
        status="open",
        source="web",
        creator_id=user.id,
    )
    db.add(ticket)
    await db.commit()

    # 返回更新后的工单列表
    result = await db.execute(
        select(Ticket)
        .where(Ticket.creator_id == user.id)
        .order_by(Ticket.created_at.desc())
    )
    tickets = result.scalars().all()
    html = await render_template("tickets/list.html", tickets=tickets)
    return fragment_response(html, request=request)


@router.get("/tickets/detail")
async def tickets_detail_fragment(
    request: Request,
    ticket_id: int,
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """工单详情片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.category),
            selectinload(Ticket.assignee),
            selectinload(Ticket.creator),
            selectinload(Ticket.comments).selectinload(TicketComment.author),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("工单不存在")
    if ticket.creator_id != user.id and not (user.is_staff or user.is_superuser):
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError("无权查看该工单")

    html = await render_template(
        "tickets/detail.html",
        ticket=ticket,
        comments=ticket.comments,
    )
    return fragment_response(html, request=request)


@router.post("/tickets/{ticket_id}/comments")
async def tickets_add_comment_fragment(
    request: Request,
    ticket_id: int,
    content: str = Form(...),
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """HTMX 表单提交工单回复，返回刷新后的工单详情片段。

    避免 POST 到 REST API（/api/v1/tickets/{id}/comments，要求 JSON body），
    HTML 表单默认 application/x-www-form-urlencoded，故走片段端点。
    """
    from app.core.exceptions import AppError, ForbiddenError, NotFoundError
    from app.models.ticket import TicketComment

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    content = content.strip()
    if not content:
        raise AppError("回复内容不能为空", "invalid_content")

    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单不存在")
    if ticket.creator_id != user.id and not (user.is_staff or user.is_superuser):
        raise ForbiddenError("无权评论该工单")

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=user.id,
        content=content,
        is_internal=False,  # 前台用户回复均为公开
    )
    db.add(comment)
    await db.commit()

    # 站内信：回复者 ≠ 工单创建者时，通知工单创建者
    # （覆盖 staff 回复用户工单的最常见场景；被动触发失败不影响主流程）
    if ticket.creator_id != user.id:
        from app.notifications.events import notify_ticket_replied

        await notify_ticket_replied(
            db,
            ticket_id=ticket.id,
            recipient_id=ticket.creator_id,
            ticket_no=ticket.ticket_no,
            site_group_id=ticket.site_group_id,
        )

    # 重新查询工单 + 评论（含 author），返回刷新后的详情片段
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.category),
            selectinload(Ticket.assignee),
            selectinload(Ticket.creator),
            selectinload(Ticket.comments).selectinload(TicketComment.author),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one()
    html = await render_template(
        "tickets/detail.html",
        ticket=ticket,
        comments=ticket.comments,
    )
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 仪表盘
# ──────────────────────────────────────────────


@router.get("/dashboard/welcome")
async def dashboard_welcome_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """仪表盘欢迎语片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    html = await render_template("dashboard/welcome.html", user=user)
    return fragment_response(html, request=request)


@router.get("/dashboard/announcement")
async def dashboard_announcement_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """站点公告片段。

    从 announcements 表读取当前租户已启用的公告，按置顶 → 排序 → 发布时间倒序展示。
    无公告时回退到默认欢迎语。
    """
    announcements: list = []
    try:
        query = select(Announcement).where(Announcement.is_active.is_(True))
        if tenant.site_group_id:
            query = query.where(
                (Announcement.site_group_id == tenant.site_group_id)
                | (Announcement.site_group_id.is_(None))
            )
        query = query.order_by(
            Announcement.is_pinned.desc(),
            Announcement.sort_order.asc(),
            Announcement.published_at.desc().nullslast(),
            Announcement.id.desc(),
        ).limit(5)
        result = await db.execute(query)
        announcements = result.scalars().all()
    except Exception:  # noqa: BLE001
        pass

    # 回退：无公告时显示默认欢迎语
    if not announcements:
        default_text = "暂无站点公告"
        try:
            result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
            sys_cfg = result.scalar_one_or_none()
            if sys_cfg is not None and sys_cfg.site_name:
                default_text = f"欢迎使用 {sys_cfg.site_name} 云服务平台"
        except Exception:  # noqa: BLE001
            pass
        html = await render_template(
            "dashboard/announcement.html",
            announcements=None,
            announcement=default_text,
        )
        return fragment_response(html, request=request)

    html = await render_template(
        "dashboard/announcement.html",
        announcements=announcements,
        announcement=None,
    )
    return fragment_response(html, request=request)


@router.get("/dashboard/stats")
async def dashboard_stats_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """仪表盘统计片段：当前用户的待处理与已解决工单数。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    pending_count = 0
    resolved_count = 0
    try:
        pending_result = await db.execute(
            select(func.count(Ticket.id)).where(
                Ticket.creator_id == user.id,
                Ticket.status.in_(["open", "pending"]),
            )
        )
        pending_count = pending_result.scalar() or 0

        resolved_result = await db.execute(
            select(func.count(Ticket.id)).where(
                Ticket.creator_id == user.id,
                Ticket.status == "resolved",
            )
        )
        resolved_count = resolved_result.scalar() or 0
    except Exception:  # noqa: BLE001
        pass

    html = await render_template(
        "dashboard/stats.html",
        pending_count=pending_count,
        resolved_count=resolved_count,
    )
    return fragment_response(html, request=request)


@router.get("/dashboard/cloud-computers")
async def dashboard_cloud_computers_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """仪表盘我的云电脑片段：取最近 4 条。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    result = await db.execute(
        select(CloudComputerUser)
        .options(selectinload(CloudComputerUser.product))
        .where(CloudComputerUser.owner_id == user.id)
        .order_by(CloudComputerUser.created_at.desc())
        .limit(4)
    )
    cloud_computers = result.scalars().all()

    html = await render_template(
        "dashboard/cloud_computers.html", cloud_computers=cloud_computers
    )
    return fragment_response(html, request=request)


@router.get("/dashboard/points")
async def dashboard_points_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """仪表盘积分余额片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    balance = 0
    try:
        filters = [UserPoints.user_id == user.id]
        if tenant.site_group_id:
            filters.append(UserPoints.site_group_id == tenant.site_group_id)
        result = await db.execute(select(UserPoints).where(*filters))
        points = result.scalar_one_or_none()
        if points is not None:
            balance = points.balance
    except Exception:  # noqa: BLE001
        pass

    html = await render_template("dashboard/points.html", balance=balance)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 积分
# ──────────────────────────────────────────────


@router.get("/points/balance")
async def points_balance_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """积分余额卡片片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    balance = 0
    try:
        filters = [UserPoints.user_id == user.id]
        if tenant.site_group_id:
            filters.append(UserPoints.site_group_id == tenant.site_group_id)
        result = await db.execute(select(UserPoints).where(*filters))
        points = result.scalar_one_or_none()
        if points is not None:
            balance = points.balance
    except Exception:  # noqa: BLE001
        pass

    html = await render_template("points/balance.html", balance=balance)
    return fragment_response(html, request=request)


async def _render_points_tasks_html(
    user: CurrentUser,
    tenant: TenantContext,
    db: AsyncSession,
) -> str:
    """渲染积分任务列表 HTML（供 GET 端点与 POST 领取端点共用）。

    对每个任务查询当前用户是否可完成（is_completable），传给模板：
    - 主动型任务（如每日签到）：可完成 → 显示"领取"按钮；不可完成 → 显示"已领取"
    - 被动型任务（如工单提交）：不显示领取按钮，仅展示任务信息
    """
    filters = [PointTask.is_active == True]  # noqa: E712
    if tenant.site_group_id:
        filters.append(
            (PointTask.site_group_id == tenant.site_group_id)
            | (PointTask.site_group_id.is_(None))
        )

    result = await db.execute(
        select(PointTask).where(*filters).order_by(PointTask.id)
    )
    tasks = result.scalars().all()

    # 查询每个任务的完成状态
    task_statuses: list[dict] = []
    for task in tasks:
        detector = point_detector_registry.get(task.detection_method)
        is_passive = detector.passive if detector else True
        completable = False
        if detector is not None and not is_passive:
            ctx = DetectorContext(
                user_id=user.id,
                task=task,
                site_group_id=tenant.site_group_id,
                db=db,
            )
            try:
                completable = await detector.is_completable(ctx)
            except Exception:  # noqa: BLE001
                completable = False
        task_statuses.append({
            "task": task,
            "completable": completable,
            "passive": is_passive,
        })

    return await render_template("points/tasks.html", task_statuses=task_statuses)


@router.get("/points/tasks")
async def points_tasks_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """积分任务列表片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)
    html = await _render_points_tasks_html(user, tenant, db)
    return fragment_response(html, request=request)


@router.post("/points/complete")
async def points_complete_task(
    request: Request,
    task_id: int = Form(...),
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """完成主动型积分任务（如每日签到领取）。

    调用 service.complete_task 发放积分，完成后返回更新后的任务列表片段，
    并通过 OOB（Out of Band）同时刷新余额卡片。
    """
    if user is None:
        return fragment_response("<div></div>", request=request)

    await points_service.complete_task(
        db,
        task_id=task_id,
        user_id=user.id,
        site_group_id=tenant.site_group_id,
    )
    await db.commit()

    # 返回更新后的任务列表 + OOB 余额刷新
    tasks_html = await _render_points_tasks_html(user, tenant, db)
    balance = await points_service.get_balance(db, user.id, tenant.site_group_id)
    balance_html = await render_template("points/balance.html", balance=balance)
    oob = f'<div id="points-balance" hx-swap-oob="outerHTML">{balance_html}</div>'
    return fragment_response(tasks_html + oob, request=request)


@router.get("/points/records")
async def points_records_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """积分明细片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    filters = [PointRecord.user_id == user.id]
    if tenant.site_group_id:
        filters.append(PointRecord.site_group_id == tenant.site_group_id)

    result = await db.execute(
        select(PointRecord)
        .options(selectinload(PointRecord.task))
        .where(*filters)
        .order_by(PointRecord.id.desc())
        .limit(50)
    )
    records = result.scalars().all()

    html = await render_template("points/records.html", records=records)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 云电脑申请
# ──────────────────────────────────────────────


@router.get("/cloud-computers/apply-form")
async def cloud_computers_apply_form_fragment(
    request: Request,
    product_id: str | int | None = None,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """云电脑申请表单片段：返回可选产品列表与申请表单。

    product_id 用于从产品列表点"申请开通"跳转时预选产品。
    """
    if user is None:
        return fragment_response("<div></div>", request=request)

    filters = [
        Product.is_available == True,  # noqa: E712
        Product.visibility == "public",
    ]
    if tenant.site_group_id:
        filters.append(
            (Product.site_group_id == tenant.site_group_id)
            | (Product.site_group_id.is_(None))
        )

    result = await db.execute(select(Product).where(*filters).order_by(Product.id))
    products = result.scalars().all()

    # 解析预选产品 ID（容忍空字符串）
    selected_product_id = None
    if product_id not in (None, ""):
        try:
            selected_product_id = int(product_id)
        except (TypeError, ValueError):
            selected_product_id = None

    html = await render_template(
        "cloud_computers/apply_form.html",
        products=products,
        selected_product_id=selected_product_id,
    )
    return fragment_response(html, request=request)


@router.post("/cloud-computers/apply")
async def cloud_computers_apply_submit(
    request: Request,
    product_id: int = Form(...),
    username: str = Form(...),
    email: str = Form(...),
    phone: str | None = Form(None),
    remarks: str | None = Form(None),
    terms_agreed: str = Form(""),  # 前端勾选同意后传 "true"
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """提交云电脑开户申请。

    创建 AccountOpeningRequest 记录（status=pending），等待管理员审批。
    提交成功后返回 toast 提示并跳转回云电脑列表。
    """
    if user is None:
        return fragment_response("<div></div>", request=request)

    # 校验产品存在且可申请
    filters = [
        Product.id == product_id,
        Product.is_available == True,  # noqa: E712
    ]
    if tenant.site_group_id:
        filters.append(
            (Product.site_group_id == tenant.site_group_id)
            | (Product.site_group_id.is_(None))
        )
    product_result = await db.execute(select(Product).where(*filters))
    product = product_result.scalar_one_or_none()
    if product is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("产品不存在或不可申请")

    # 使用条款校验：若产品配置了 terms，则前端必须勾选同意（terms_agreed="true"）才能提交
    # 前端 JS 在按钮启用时自动注入隐藏字段；此处为后端兜底，防绕过
    if product.terms and product.terms.strip():
        from app.core.exceptions import AppError

        if terms_agreed != "true":
            raise AppError(
                "请阅读并同意产品使用条款后再提交申请",
                "terms_not_agreed",
            )

    # 积分余额预检：申请时余额须 ≥ 产品所需积分，否则直接拒绝
    # （实际扣分发生在管理员审核通过、开通成功后，避免申请被拒时误扣）
    if product.required_points and product.required_points > 0:
        from app.core.exceptions import AppError

        balance = await points_service.get_balance(
            db, user.id, tenant.site_group_id
        )
        if balance < product.required_points:
            raise AppError(
                f"积分不足：当前余额 {balance}，该产品需 {product.required_points} 积分/月",
                "insufficient_points",
            )

    # 创建开户申请
    req = AccountOpeningRequest(
        applicant_id=user.id,
        contact_email=email,
        contact_phone=phone,
        username=username,
        user_email=email,
        user_description=remarks,
        target_product_id=product_id,
        status="pending",
    )
    db.add(req)
    await db.commit()

    # 返回 toast 提示 + 跳转脚本
    html = (
        '<div hx-swap-oob="true" id="toast" '
        'style="position:fixed;top:16px;right:16px;z-index:9999;'
        'background:#16a34a;color:#fff;padding:12px 16px;border-radius:8px;'
        'box-shadow:0 4px 12px rgba(0,0,0,0.15);font-size:14px;">'
        '申请已提交，等待管理员审批</div>'
        '<script>setTimeout(function(){location.href="/cloud-computers";},1500);</script>'
    )
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 我的云电脑（运行中实例 + 开户申请）
# ──────────────────────────────────────────────


@router.get("/my-cloud/list")
async def my_cloud_list_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """我的云电脑列表片段：合并运行中实例（CloudComputerUser）与申请中开户请求。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    # 运行中实例（含 product 用于显示产品名）
    active_result = await db.execute(
        select(CloudComputerUser)
        .options(selectinload(CloudComputerUser.product))
        .where(CloudComputerUser.owner_id == user.id)
        .order_by(CloudComputerUser.created_at.desc())
    )
    active_clouds = active_result.scalars().all()

    # 申请中开户请求（含 target_product）
    pending_result = await db.execute(
        select(AccountOpeningRequest)
        .options(selectinload(AccountOpeningRequest.target_product))
        .where(AccountOpeningRequest.applicant_id == user.id)
        .order_by(AccountOpeningRequest.created_at.desc())
    )
    pending_requests = pending_result.scalars().all()

    html = await render_template(
        "my_cloud/list.html",
        active_clouds=active_clouds,
        pending_requests=pending_requests,
    )
    return fragment_response(html, request=request)


@router.get("/my-cloud/detail")
async def my_cloud_detail_fragment(
    request: Request,
    cloud_user_id: int | None = None,
    request_id: int | None = None,
    user: CurrentUser | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """我的云电脑详情片段：按 cloud_user_id 渲染运行中详情，按 request_id 渲染申请中详情。"""
    from app.core.exceptions import NotFoundError

    if user is None:
        return fragment_response("<div></div>", request=request)

    if cloud_user_id:
        # 运行中实例详情
        result = await db.execute(
            select(CloudComputerUser)
            .options(
                selectinload(CloudComputerUser.product).selectinload(Product.host),
            )
            .where(CloudComputerUser.id == cloud_user_id)
        )
        ccu = result.scalar_one_or_none()
        if ccu is None:
            raise NotFoundError("云电脑不存在")
        if ccu.owner_id != user.id and not (user.is_staff or user.is_superuser):
            raise NotFoundError("云电脑不存在")

        html = await render_template("my_cloud/detail_active.html", ccu=ccu)
        return fragment_response(html, request=request)

    if request_id:
        # 申请中详情
        result = await db.execute(
            select(AccountOpeningRequest)
            .options(selectinload(AccountOpeningRequest.target_product))
            .where(AccountOpeningRequest.id == request_id)
        )
        req = result.scalar_one_or_none()
        if req is None:
            raise NotFoundError("开户申请不存在")
        if req.applicant_id != user.id and not (user.is_staff or user.is_superuser):
            raise NotFoundError("开户申请不存在")

        html = await render_template("my_cloud/detail_pending.html", req=req)
        return fragment_response(html, request=request)

    raise NotFoundError("未指定详情对象")


@router.post("/my-cloud/{cloud_user_id}/view-password")
async def my_cloud_view_password_fragment(
    request: Request,
    cloud_user_id: int,
    user: CurrentUser | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """查看初始密码（阅后即焚）：解密并展示一次，随后清除密文。

    返回刷新后的运行中详情片段。
    """
    from app.core.exceptions import AppError, NotFoundError
    from app.security.field_cipher import decrypt_field

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    result = await db.execute(
        select(CloudComputerUser)
        .options(selectinload(CloudComputerUser.product).selectinload(Product.host))
        .where(CloudComputerUser.id == cloud_user_id)
    )
    ccu = result.scalar_one_or_none()
    if ccu is None:
        raise NotFoundError("云电脑不存在")
    if ccu.owner_id != user.id:
        raise NotFoundError("云电脑不存在")
    if ccu.password_viewed or not ccu.initial_password_cipher:
        raise AppError("密码已查看或不存在", "password_unavailable")

    password = decrypt_field(
        ccu.initial_password_cipher, "cloud_computer_user.initial_password"
    )
    # 阅后即焚：标记已查看 + 清除密文
    ccu.password_viewed = True
    from datetime import datetime, timezone

    ccu.password_viewed_at = datetime.now(timezone.utc)
    ccu.initial_password_cipher = None
    await db.commit()

    html = await render_template(
        "my_cloud/detail_active.html", ccu=ccu, revealed_password=password
    )
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 个人资料
# ──────────────────────────────────────────────


@router.get("/profile/detail")
async def profile_detail_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """个人资料片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    html = await render_template("profile/detail.html", user=user)
    return fragment_response(html, request=request)


@router.get("/profile/change-password-form")
async def profile_change_password_form_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """修改密码表单片段。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    html = await render_template("profile/change_password_form.html")
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 邮箱管理
# ──────────────────────────────────────────────

# 单个用户最多绑定的邮箱数（含主邮箱），与设计稿「最多 4 个其他邮箱 + 1 主邮箱」一致
_MAX_USER_EMAILS = 5


async def _render_email_list_html(user: CurrentUser, db: AsyncSession) -> str:
    """渲染用户邮箱列表 HTML（主邮箱 + 其他邮箱）。

    供 GET 端点与 POST/DELETE 操作端点共用：写操作完成后重新查询并返回刷新后的列表，
    前端 HTMX 据此无刷新更新。
    """
    from app.models.user import UserEmail

    result = await db.execute(
        select(UserEmail)
        .where(UserEmail.user_id == user.id)
        .order_by(UserEmail.is_primary.desc(), UserEmail.created_at.asc())
    )
    emails = result.scalars().all()

    primary_email = next((e for e in emails if e.is_primary), None)
    secondary_emails = [e for e in emails if not e.is_primary]

    return await render_template(
        "profile/email_list.html",
        primary_email=primary_email,
        secondary_emails=secondary_emails,
    )


@router.get("/profile/emails")
async def profile_emails_fragment(
    request: Request,
    user: CurrentUser | None = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """邮箱列表片段：主邮箱 + 其他邮箱（含验证状态与操作按钮）。"""
    if user is None:
        return fragment_response("<div></div>", request=request)

    html = await _render_email_list_html(user, db)
    return fragment_response(html, request=request)


@router.post("/profile/emails/add")
async def profile_email_add(
    request: Request,
    email: str = Form(...),
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """添加新邮箱（默认 is_primary=False, is_verified=False）。

    返回 JSON（前端 JS 处理 toast 与列表刷新），不直接返回片段，
    便于失败时在对话框内显示具体错误。
    """
    from app.core.exceptions import AppError
    from app.models.user import UserEmail

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    email = email.strip().lower()
    if not email:
        raise AppError("邮箱不能为空", "invalid_email")

    # 简单格式校验
    import re

    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        raise AppError("邮箱格式不正确", "invalid_email")

    # 数量上限校验
    count_result = await db.execute(
        select(func.count(UserEmail.id)).where(UserEmail.user_id == user.id)
    )
    if (count_result.scalar() or 0) >= _MAX_USER_EMAILS:
        raise AppError(f"每个账号最多绑定 {_MAX_USER_EMAILS} 个邮箱", "email_limit_exceeded")

    # 唯一性校验：跨用户也禁止重复（与 User.email 全局唯一策略保持一致）
    existing = await db.execute(select(UserEmail).where(UserEmail.email == email))
    if existing.scalar_one_or_none() is not None:
        raise AppError("该邮箱已被绑定", "email_exists")

    new_email = UserEmail(
        user_id=user.id,
        email=email,
        is_primary=False,
        is_verified=False,
    )
    db.add(new_email)
    await db.commit()

    return {"success": True}


@router.post("/profile/emails/{email_id}/set-primary")
async def profile_email_set_primary(
    request: Request,
    email_id: int,
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """将指定邮箱设为主邮箱，原主邮箱降级为普通邮箱。

    要求目标邮箱已通过验证（未验证邮箱不可设为主邮箱）。
    同步更新 User.email 字段，保持与主邮箱一致。
    """
    from app.core.exceptions import AppError, NotFoundError
    from app.models.user import UserEmail

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    result = await db.execute(
        select(UserEmail).where(UserEmail.id == email_id, UserEmail.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("邮箱不存在")

    if not target.is_verified:
        raise AppError("未验证的邮箱无法设为主邮箱", "email_not_verified")

    if target.is_primary:
        # 已是主邮箱，幂等返回
        return {"success": True}

    # 将原主邮箱降级
    primary_result = await db.execute(
        select(UserEmail).where(
            UserEmail.user_id == user.id,
            UserEmail.is_primary == True,  # noqa: E712
        )
    )
    old_primary = primary_result.scalar_one_or_none()
    if old_primary is not None:
        old_primary.is_primary = False

    # 提升目标邮箱
    target.is_primary = True
    # 同步 User.email 字段（保持与主邮箱一致，便于全局唯一约束与登录校验）
    user.db_user.email = target.email if user.db_user else None

    await db.commit()
    return {"success": True}


@router.post("/profile/emails/{email_id}/delete")
async def profile_email_delete(
    request: Request,
    email_id: int,
    user: CurrentUser = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """删除指定邮箱。

    禁止删除主邮箱（需先将其他邮箱设为主邮箱再删除原主邮箱）。
    删除非主邮箱不影响 User.email 字段。
    """
    from app.core.exceptions import AppError, NotFoundError
    from app.models.user import UserEmail

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    result = await db.execute(
        select(UserEmail).where(UserEmail.id == email_id, UserEmail.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("邮箱不存在")

    if target.is_primary:
        raise AppError("不能删除主邮箱，请先切换主邮箱", "cannot_delete_primary")

    await db.delete(target)
    await db.commit()
    return {"success": True}


@router.post("/profile/emails/{email_id}/send-verification")
async def profile_email_send_verification(
    request: Request,
    email_id: int,
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """向指定未验证邮箱发送验证邮件。

    依赖 SMTP 配置：若全局/站点组均未配置 SMTP，则返回友好错误，
    前端 toast 提示用户联系管理员。
    """
    from app.core.exceptions import AppError, NotFoundError
    from app.models.user import UserEmail
    from app.services.email import resolve_smtp_config

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    result = await db.execute(
        select(UserEmail).where(UserEmail.id == email_id, UserEmail.user_id == user.id)
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("邮箱不存在")

    if target.is_verified:
        return {"success": True, "email_sent": False, "message": "该邮箱已验证"}

    # SMTP 配置校验
    smtp_cfg = await resolve_smtp_config(db, tenant)
    if smtp_cfg is None or not smtp_cfg.is_configured:
        raise AppError(
            "邮箱验证功能未启用，请联系管理员配置 SMTP",
            "smtp_not_configured",
        )

    # TODO: 实现完整的邮箱验证流程（签发验证 token → 发送验证链接邮件 → 回调端点校验）
    # 当前仅占位返回，避免在缺少验证回调端点的情况下误导用户
    raise AppError(
        "邮箱验证功能暂未开放，请联系管理员",
        "verification_unavailable",
    )


# ──────────────────────────────────────────────
# 站内信
# ──────────────────────────────────────────────


async def _render_notifications_list_html(
    user: CurrentUser,
    tenant: TenantContext,
    db: AsyncSession,
    filter: str = "all",
) -> str:
    """渲染站内信列表 HTML（供 GET 端点与 POST 写操作端点共用）。

    写操作成功后重新查询并返回刷新后的列表，与积分模块的渲染共用模式一致。
    """
    from app.notifications import service as notif_service
    from app.notifications.types import TYPE_META

    notifications = await notif_service.get_user_notifications(
        db, user.id, filter=filter, site_group_id=tenant.site_group_id
    )
    return await render_template(
        "notifications/list.html",
        notifications=notifications,
        type_meta=TYPE_META,
        current_filter=filter,
    )


@router.get("/notifications/list")
async def notifications_list_fragment(
    request: Request,
    filter: str = "all",
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """站内信列表片段。

    filter 可选：all / unread / system / ticket / points / security / product / maintenance。
    """
    if user is None:
        return fragment_response("<div></div>", request=request)
    html = await _render_notifications_list_html(user, tenant, db, filter)
    return fragment_response(html, request=request)


@router.get("/notifications/unread-count")
async def notifications_unread_count_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """未读数徽章片段（顶栏铃铛角标）。

    嵌入到铃铛容器内（id="notification-badge"），HTMX load 用 innerHTML 填充；
    写操作后通过 OOB 整块替换 #notification-badge（由调用端点附加 OOB 包裹）。
    """
    from app.notifications import service as notif_service

    if user is None:
        return fragment_response("", request=request)

    count = await notif_service.get_unread_count(
        db, user.id, site_group_id=tenant.site_group_id
    )
    html = await render_template("notifications/badge.html", unread_count=count)
    return fragment_response(html, request=request)


@router.post("/notifications/{notification_id}/read")
async def notifications_mark_read_fragment(
    request: Request,
    notification_id: int,
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """标记单条已读，返回刷新后的列表 + OOB 未读徽章。

    filter 通过查询参数 filter 传入（默认 all），保持当前过滤上下文。
    """
    from app.core.exceptions import AppError
    from app.notifications import service as notif_service

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    filter = request.query_params.get("filter", "all")
    await notif_service.mark_as_read(db, notification_id, user.id)
    await db.commit()

    tasks_html = await _render_notifications_list_html(user, tenant, db, filter)
    count = await notif_service.get_unread_count(
        db, user.id, site_group_id=tenant.site_group_id
    )
    badge_html = await render_template("notifications/badge.html", unread_count=count)
    oob = f'<span id="notification-badge" hx-swap-oob="true">{badge_html}</span>'
    return fragment_response(tasks_html + oob, request=request)


@router.post("/notifications/read-all")
async def notifications_mark_all_read_fragment(
    request: Request,
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """全部已读，返回刷新后的列表 + OOB 未读徽章。"""
    from app.core.exceptions import AppError
    from app.notifications import service as notif_service

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    filter = request.query_params.get("filter", "all")
    await notif_service.mark_all_as_read(
        db, user.id, site_group_id=tenant.site_group_id
    )
    await db.commit()

    tasks_html = await _render_notifications_list_html(user, tenant, db, filter)
    count = await notif_service.get_unread_count(
        db, user.id, site_group_id=tenant.site_group_id
    )
    badge_html = await render_template("notifications/badge.html", unread_count=count)
    oob = f'<span id="notification-badge" hx-swap-oob="true">{badge_html}</span>'
    return fragment_response(tasks_html + oob, request=request)


@router.post("/notifications/{notification_id}/delete")
async def notifications_delete_fragment(
    request: Request,
    notification_id: int,
    user: CurrentUser = Depends(get_current_user_optional),
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    """删除单条站内信，返回刷新后的列表 + OOB 未读徽章。"""
    from app.core.exceptions import AppError
    from app.notifications import service as notif_service

    if user is None:
        raise AppError("请先登录", "unauthenticated")

    filter = request.query_params.get("filter", "all")
    await notif_service.delete_notification(db, notification_id, user.id)
    await db.commit()

    tasks_html = await _render_notifications_list_html(user, tenant, db, filter)
    count = await notif_service.get_unread_count(
        db, user.id, site_group_id=tenant.site_group_id
    )
    badge_html = await render_template("notifications/badge.html", unread_count=count)
    oob = f'<span id="notification-badge" hx-swap-oob="true">{badge_html}</span>'
    return fragment_response(tasks_html + oob, request=request)
