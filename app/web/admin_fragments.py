"""后台管理 HTMX 片段（不可缓存、仅 staff/superuser）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import require_staff
from app.cache.fragments import fragment_response
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models.announcement import Announcement
from app.models.host import Host
from app.models.operations import Product, ProductGroup
from app.models.ticket import Ticket
from app.templates import render_template
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/fragments/admin", tags=["admin-fragments"])


def _parse_int_or_none(raw: str | int | None) -> int | None:
    """从 query 参数解析 int | None，容忍空字符串。

    前端模板渲染时常产出 ``?id=`` 这样的空值参数，FastAPI 直接用 ``int | None``
    会因空字符串无法解析为 int 而报 422。统一在此转换为 int | None。
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────
# 主机管理
# ──────────────────────────────────────────────


@router.get("/hosts/list")
async def admin_hosts_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台主机列表片段。"""
    query = select(Host).order_by(Host.id.desc())
    if tenant.site_group_id:
        query = query.where(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(query)
    hosts = result.scalars().all()
    html = await render_template("admin/hosts_list.html", hosts=hosts)
    return fragment_response(html, request=request)


@router.get("/hosts/form")
async def admin_hosts_form(
    request: Request,
    host_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台主机创建/编辑表单片段。

    host_id 用 str | int | None 容忍前端模板渲染出的空字符串 ``?host_id=``，
    用 _parse_int_or_none 统一转换为 int | None，避免 FastAPI 422。
    """
    hid = _parse_int_or_none(host_id)
    host = None
    if hid:
        query = select(Host).where(Host.id == hid)
        if tenant.site_group_id:
            query = query.where(
                (Host.site_group_id == tenant.site_group_id)
                | (Host.site_group_id.is_(None))
            )
        result = await db.execute(query)
        host = result.scalar_one_or_none()
        if host is None:
            raise NotFoundError("主机不存在")
    html = await render_template("admin/hosts_form.html", host=host)
    return fragment_response(html, request=request)


@router.post("/hosts/create")
async def admin_hosts_create(
    request: Request,
    name: str = Form(),
    hostname: str = Form(),
    connection_type: str = Form("winrm"),
    auth_method: str = Form("ntlm"),
    port: int = Form(5985),
    rdp_port: int = Form(3389),
    use_ssl: bool = Form(False),
    username: str | None = Form(None),
    password: str | None = Form(None),
    description: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台创建主机并返回列表片段。"""
    from app.security.field_cipher import encrypt_field

    host = Host(
        name=name,
        hostname=hostname,
        connection_type=connection_type,
        auth_method=auth_method,
        port=port,
        rdp_port=rdp_port,
        use_ssl=use_ssl,
        username=username,
        password_cipher=encrypt_field(password, "host.password") if password else None,
        description=description,
        created_by_id=user.id,
        site_group_id=tenant.site_group_id,
        status="active",
    )
    db.add(host)
    await db.commit()
    return await admin_hosts_list(request, db, tenant, user)


@router.put("/hosts/{host_id}")
async def admin_hosts_update(
    request: Request,
    host_id: int,
    name: str = Form(),
    hostname: str = Form(),
    connection_type: str = Form("winrm"),
    auth_method: str = Form("ntlm"),
    port: int = Form(5985),
    rdp_port: int = Form(3389),
    use_ssl: bool = Form(False),
    username: str | None = Form(None),
    password: str | None = Form(None),
    description: str | None = Form(None),
    is_active: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台更新主机并返回列表片段。"""
    from app.security.field_cipher import encrypt_field

    filters = [Host.id == host_id]
    if tenant.site_group_id:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters))
    host = result.scalar_one_or_none()
    if host is None:
        raise NotFoundError("主机不存在")

    # checkbox 未选中时不会提交字段，转换为状态值
    status = "active" if is_active else "inactive"

    update_data = {
        "name": name,
        "hostname": hostname,
        "connection_type": connection_type,
        "auth_method": auth_method,
        "port": port,
        "rdp_port": rdp_port,
        "use_ssl": use_ssl,
        "username": username,
        "status": status,
        "description": description,
    }
    if password:
        update_data["password_cipher"] = encrypt_field(password, "host.password")

    for key, value in update_data.items():
        setattr(host, key, value)

    await db.commit()
    return await admin_hosts_list(request, db, tenant, user)


@router.post("/hosts/{host_id}/test")
async def admin_hosts_test(
    request: Request,
    host_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台测试主机连接并返回 HTML 结果片段。"""
    from app.winrm.client import AsyncWinRMClient

    filters = [Host.id == host_id]
    if tenant.site_group_id:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters))
    host = result.scalar_one_or_none()
    if host is None:
        raise NotFoundError("主机不存在")

    try:
        client = await AsyncWinRMClient.from_host_config(host)
        try:
            res = await client.execute_command("whoami")
            if res.success:
                html = f'<span class="badge badge-active">连接成功: {res.std_out.strip()}</span>'
            else:
                html = f'<span class="badge badge-disabled">连接失败: {res.std_err or "未知错误"}</span>'
        finally:
            await client.close()
    except Exception as e:  # noqa: BLE001
        html = f'<span class="badge badge-disabled">连接失败: {str(e)}</span>'

    return fragment_response(html, request=request)


@router.delete("/hosts/{host_id}")
async def admin_hosts_delete(
    request: Request,
    host_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台删除主机并返回列表片段。"""
    filters = [Host.id == host_id]
    if tenant.site_group_id:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters))
    host = result.scalar_one_or_none()
    if host is None:
        raise NotFoundError("主机不存在")
    await db.delete(host)
    await db.commit()
    return await admin_hosts_list(request, db, tenant, user)


# ──────────────────────────────────────────────
# 产品管理
# ──────────────────────────────────────────────


@router.get("/products/groups")
async def admin_product_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台产品组列表片段。"""
    query = select(ProductGroup).order_by(ProductGroup.display_order, ProductGroup.id)
    if tenant.site_group_id:
        query = query.where(
            (ProductGroup.site_group_id == tenant.site_group_id)
            | (ProductGroup.site_group_id.is_(None))
        )
    result = await db.execute(query)
    groups = result.scalars().all()
    html = await render_template("admin/product_groups.html", groups=groups)
    return fragment_response(html, request=request)


@router.get("/products/list")
async def admin_products_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台产品列表片段。"""
    query = select(Product).order_by(Product.id.desc())
    if tenant.site_group_id:
        query = query.where(
            (Product.site_group_id == tenant.site_group_id)
            | (Product.site_group_id.is_(None))
        )
    result = await db.execute(query)
    products = result.scalars().all()

    groups_result = await db.execute(
        select(ProductGroup).order_by(ProductGroup.display_order, ProductGroup.id)
    )
    groups = {g.id: g.name for g in groups_result.scalars().all()}

    hosts_result = await db.execute(select(Host.id, Host.name).order_by(Host.id))
    hosts = {h.id: h.name for h in hosts_result.mappings().all()}

    html = await render_template(
        "admin/products_list.html",
        products=products,
        groups=groups,
        hosts=hosts,
    )
    return fragment_response(html, request=request)


@router.get("/products/form")
async def admin_products_form(
    request: Request,
    product_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台产品创建/编辑表单片段。"""
    pid = _parse_int_or_none(product_id)
    product = None
    if pid:
        query = select(Product).where(Product.id == pid)
        if tenant.site_group_id:
            query = query.where(
                (Product.site_group_id == tenant.site_group_id)
                | (Product.site_group_id.is_(None))
            )
        result = await db.execute(query)
        product = result.scalar_one_or_none()
        if product is None:
            raise NotFoundError("产品不存在")

    groups_result = await db.execute(
        select(ProductGroup).order_by(ProductGroup.display_order, ProductGroup.id)
    )
    groups = groups_result.scalars().all()

    hosts_result = await db.execute(select(Host).order_by(Host.id))
    hosts = hosts_result.scalars().all()

    html = await render_template(
        "admin/products_form.html",
        product=product,
        groups=groups,
        hosts=hosts,
    )
    return fragment_response(html, request=request)


@router.post("/products/create")
async def admin_products_create(
    request: Request,
    name: str = Form(),
    display_name: str | None = Form(None),
    description: str | None = Form(None),
    display_description: str | None = Form(None),
    product_group_id: str | None = Form(None),
    host_id: int = Form(),
    rdp_port: int = Form(3389),
    display_hostname: str | None = Form(None),
    is_available: bool = Form(False),
    auto_approval: bool = Form(False),
    visibility: str = Form("public"),
    limit_one_per_user: bool = Form(False),
    required_points: int = Form(0),
    terms: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台创建产品并返回列表片段。"""
    # 处理空字符串（select 选 "无" 时 value=""）
    product_group_id_int: int | None = None
    if product_group_id:
        try:
            product_group_id_int = int(product_group_id)
        except (TypeError, ValueError):
            raise NotFoundError("产品组不存在") from None

    # 校验主机
    host_filters = [Host.id == host_id]
    if tenant.site_group_id and not user.is_superuser:
        host_filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    host_result = await db.execute(select(Host).where(*host_filters))
    if host_result.scalar_one_or_none() is None:
        raise NotFoundError("主机不存在")

    # 校验产品组
    if product_group_id_int is not None:
        pg_filters = [ProductGroup.id == product_group_id_int]
        if tenant.site_group_id and not user.is_superuser:
            pg_filters.append(
                (ProductGroup.site_group_id == tenant.site_group_id)
                | (ProductGroup.site_group_id.is_(None))
            )
        pg_result = await db.execute(select(ProductGroup).where(*pg_filters))
        if pg_result.scalar_one_or_none() is None:
            raise NotFoundError("产品组不存在")

    product = Product(
        name=name,
        description=description,
        display_name=display_name,
        display_description=display_description,
        product_group_id=product_group_id_int,
        host_id=host_id,
        site_group_id=tenant.site_group_id,
        rdp_port=rdp_port,
        display_hostname=display_hostname,
        is_available=is_available,
        auto_approval=auto_approval,
        visibility=visibility,
        limit_one_per_user=limit_one_per_user,
        required_points=required_points,
        terms=terms.strip() if terms else None,  # 空白字符串归一化为 None
        created_by_id=user.id,
    )
    db.add(product)
    await db.commit()
    return await admin_products_list(request, db, tenant, user)


@router.put("/products/{product_id}")
async def admin_products_update(
    request: Request,
    product_id: int,
    name: str = Form(),
    display_name: str | None = Form(None),
    description: str | None = Form(None),
    display_description: str | None = Form(None),
    product_group_id: str | None = Form(None),
    host_id: int = Form(),
    rdp_port: int = Form(3389),
    display_hostname: str | None = Form(None),
    is_available: bool = Form(False),
    auto_approval: bool = Form(False),
    visibility: str = Form("public"),
    limit_one_per_user: bool = Form(False),
    required_points: int = Form(0),
    terms: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台更新产品并返回列表片段。"""
    # 处理空字符串（select 选 "无" 时 value=""）
    product_group_id_int: int | None = None
    if product_group_id:
        try:
            product_group_id_int = int(product_group_id)
        except (TypeError, ValueError):
            raise NotFoundError("产品组不存在") from None

    filters = [Product.id == product_id]
    if tenant.site_group_id:
        filters.append(
            (Product.site_group_id == tenant.site_group_id)
            | (Product.site_group_id.is_(None))
        )
    result = await db.execute(select(Product).where(*filters))
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("产品不存在")

    # 校验主机
    host_filters = [Host.id == host_id]
    if tenant.site_group_id and not user.is_superuser:
        host_filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    host_result = await db.execute(select(Host).where(*host_filters))
    if host_result.scalar_one_or_none() is None:
        raise NotFoundError("主机不存在")

    # 校验产品组
    if product_group_id_int is not None:
        pg_filters = [ProductGroup.id == product_group_id_int]
        if tenant.site_group_id and not user.is_superuser:
            pg_filters.append(
                (ProductGroup.site_group_id == tenant.site_group_id)
                | (ProductGroup.site_group_id.is_(None))
            )
        pg_result = await db.execute(select(ProductGroup).where(*pg_filters))
        if pg_result.scalar_one_or_none() is None:
            raise NotFoundError("产品组不存在")

    product.name = name
    product.description = description
    product.display_name = display_name
    product.display_description = display_description
    product.product_group_id = product_group_id_int
    product.host_id = host_id
    product.rdp_port = rdp_port
    product.display_hostname = display_hostname
    product.is_available = is_available
    product.auto_approval = auto_approval
    product.visibility = visibility
    product.limit_one_per_user = limit_one_per_user
    product.required_points = required_points
    product.terms = terms.strip() if terms else None  # 空白字符串归一化为 None

    await db.commit()
    return await admin_products_list(request, db, tenant, user)


@router.delete("/products/{product_id}")
async def admin_products_delete(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台删除产品并返回列表片段。"""
    filters = [Product.id == product_id]
    if tenant.site_group_id:
        filters.append(
            (Product.site_group_id == tenant.site_group_id)
            | (Product.site_group_id.is_(None))
        )
    result = await db.execute(select(Product).where(*filters))
    product = result.scalar_one_or_none()
    if product is None:
        raise NotFoundError("产品不存在")
    await db.delete(product)
    await db.commit()
    return await admin_products_list(request, db, tenant, user)


# ──────────────────────────────────────────────
# 工单管理
# ──────────────────────────────────────────────


@router.get("/tickets/list")
async def admin_tickets_list(
    request: Request,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台工单列表片段。"""
    query = select(Ticket).order_by(Ticket.created_at.desc())
    if tenant.site_group_id:
        query = query.where(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    if status:
        query = query.where(Ticket.status == status)
    result = await db.execute(query)
    tickets = result.scalars().all()
    html = await render_template("admin/tickets_list.html", tickets=tickets, status=status)
    return fragment_response(html, request=request)


@router.get("/tickets/detail")
async def admin_tickets_detail(
    request: Request,
    ticket_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台工单详情片段。

    ticket_id 用 str | int | None 容忍前端模板渲染出的空字符串 ``?ticket_id=``，
    用 _parse_int_or_none 统一转换为 int | None，避免 FastAPI 422。
    """
    tid = _parse_int_or_none(ticket_id)
    if not tid:
        raise NotFoundError("工单不存在")
    query = (
        select(Ticket)
        .options(selectinload(Ticket.comments))
        .where(Ticket.id == tid)
    )
    if tenant.site_group_id:
        query = query.where(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    result = await db.execute(query)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单不存在")

    html = await render_template(
        "admin/tickets_detail.html",
        ticket=ticket,
        comments=ticket.comments,
    )
    return fragment_response(html, request=request)


@router.put("/tickets/{ticket_id}")
async def admin_tickets_update(
    request: Request,
    ticket_id: int,
    status: str = Form(...),
    priority: str = Form(...),
    assignee_id: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台更新工单并返回详情片段。"""
    filters = [Ticket.id == ticket_id]
    if tenant.site_group_id:
        filters.append(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.comments))
        .where(*filters)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单不存在")

    ticket.status = status
    ticket.priority = priority
    ticket.assignee_id = assignee_id or None
    await db.commit()
    await db.refresh(ticket)

    html = await render_template(
        "admin/tickets_detail.html",
        ticket=ticket,
        comments=ticket.comments,
    )
    return fragment_response(html, request=request)


@router.post("/tickets/{ticket_id}/comments")
async def admin_tickets_add_comment(
    request: Request,
    ticket_id: int,
    content: str = Form(...),
    is_internal: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台添加工单评论并返回详情片段。"""
    from app.models.ticket import TicketComment

    filters = [Ticket.id == ticket_id]
    if tenant.site_group_id:
        filters.append(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    result = await db.execute(
        select(Ticket)
        .options(selectinload(Ticket.comments))
        .where(*filters)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单不存在")

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=user.id,
        content=content,
        is_internal=is_internal,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(ticket)

    html = await render_template(
        "admin/tickets_detail.html",
        ticket=ticket,
        comments=ticket.comments,
    )
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 公告管理
# ──────────────────────────────────────────────


def _announcement_tenant_filter(tenant: TenantContext):
    """构建公告的站点过滤条件：当前租户或全局（NULL）。"""
    if not tenant.site_group_id:
        return []
    return [
        (Announcement.site_group_id == tenant.site_group_id)
        | (Announcement.site_group_id.is_(None))
    ]


@router.get("/announcements/list")
async def admin_announcements_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台公告列表片段。

    排序：置顶优先 → sort_order 升序 → 发布时间倒序 → id 倒序。
    """
    query = select(Announcement)
    for cond in _announcement_tenant_filter(tenant):
        query = query.where(cond)
    query = query.order_by(
        Announcement.is_pinned.desc(),
        Announcement.sort_order.asc(),
        Announcement.published_at.desc().nullslast(),
        Announcement.id.desc(),
    )
    result = await db.execute(query)
    announcements = result.scalars().all()
    html = await render_template(
        "admin/announcements_list.html", announcements=announcements
    )
    return fragment_response(html, request=request)


@router.get("/announcements/form")
async def admin_announcements_form(
    request: Request,
    announcement_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台公告创建/编辑表单片段。"""
    aid = _parse_int_or_none(announcement_id)
    announcement = None
    if aid:
        query = select(Announcement).where(Announcement.id == aid)
        for cond in _announcement_tenant_filter(tenant):
            query = query.where(cond)
        result = await db.execute(query)
        announcement = result.scalar_one_or_none()
        if announcement is None:
            raise NotFoundError("公告不存在")
    html = await render_template(
        "admin/announcements_form.html", announcement=announcement
    )
    return fragment_response(html, request=request)


@router.post("/announcements/create")
async def admin_announcements_create(
    request: Request,
    title: str = Form(),
    content: str = Form(),
    is_pinned: bool = Form(False),
    is_active: bool = Form(False),
    sort_order: int = Form(0),
    published_at: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台创建公告并返回列表片段。"""
    from datetime import datetime

    published_dt: datetime | None = None
    if published_at:
        # datetime-local 输入格式：YYYY-MM-DDTHH:MM
        try:
            published_dt = datetime.fromisoformat(published_at)
        except ValueError:
            published_dt = None

    announcement = Announcement(
        title=title.strip(),
        content=content,
        is_pinned=is_pinned,
        is_active=is_active,
        sort_order=sort_order,
        published_at=published_dt,
        created_by_id=user.id,
        site_group_id=tenant.site_group_id,
    )
    db.add(announcement)
    await db.commit()
    return await admin_announcements_list(request, db, tenant, user)


@router.put("/announcements/{announcement_id}")
async def admin_announcements_update(
    request: Request,
    announcement_id: int,
    title: str = Form(),
    content: str = Form(),
    is_pinned: bool = Form(False),
    is_active: bool = Form(False),
    sort_order: int = Form(0),
    published_at: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台更新公告并返回列表片段。"""
    from datetime import datetime

    filters = [Announcement.id == announcement_id]
    filters.extend(_announcement_tenant_filter(tenant))
    result = await db.execute(select(Announcement).where(*filters))
    announcement = result.scalar_one_or_none()
    if announcement is None:
        raise NotFoundError("公告不存在")

    published_dt: datetime | None = None
    if published_at:
        try:
            published_dt = datetime.fromisoformat(published_at)
        except ValueError:
            published_dt = None

    announcement.title = title.strip()
    announcement.content = content
    announcement.is_pinned = is_pinned
    announcement.is_active = is_active
    announcement.sort_order = sort_order
    announcement.published_at = published_dt

    await db.commit()
    return await admin_announcements_list(request, db, tenant, user)


@router.delete("/announcements/{announcement_id}")
async def admin_announcements_delete(
    request: Request,
    announcement_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台删除公告并返回列表片段。"""
    filters = [Announcement.id == announcement_id]
    filters.extend(_announcement_tenant_filter(tenant))
    result = await db.execute(select(Announcement).where(*filters))
    announcement = result.scalar_one_or_none()
    if announcement is None:
        raise NotFoundError("公告不存在")
    await db.delete(announcement)
    await db.commit()
    return await admin_announcements_list(request, db, tenant, user)


# ──────────────────────────────────────────────
# 站内信推送
# ──────────────────────────────────────────────


async def _render_notifications_admin_list(
    db: AsyncSession, tenant: TenantContext
) -> str:
    """渲染后台站内信列表片段（写操作后复用，确保返回刷新后的列表）。"""
    from app.notifications import service as notif_service

    notifications = await notif_service.admin_list_notifications(
        db, site_group_id=tenant.site_group_id, limit=100
    )
    return await render_template(
        "admin/notifications_list.html", notifications=notifications
    )


@router.get("/notifications/list")
async def admin_notifications_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台站内信列表片段（admin 视角，按 site_group_id 过滤，预加载 user）。"""
    html = await _render_notifications_admin_list(db, tenant)
    return fragment_response(html, request=request)


@router.get("/notifications/form")
async def admin_notifications_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台新建推送表单片段。"""
    html = await render_template("admin/notifications_form.html")
    return fragment_response(html, request=request)


@router.get("/notifications/users/search")
async def admin_notifications_users_search(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """站内信推送：按用户名搜索用户，返回下拉候选片段。"""
    from app.notifications import service as notif_service

    q = (q or "").strip()
    if not q:
        return fragment_response("", request=request)

    users = await notif_service.search_users_for_push(db, keyword=q, limit=10)
    html = await render_template(
        "admin/notifications_users_search.html", users=users
    )
    return fragment_response(html, request=request)


@router.post("/notifications/create")
async def admin_notifications_create(
    request: Request,
    target_type: str = Form(...),
    type: str = Form(...),
    level: str = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    body: str | None = Form(None),
    action_url: str | None = Form(None),
    user_ids: list[int] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台创建站内信推送。

    - target_type=all：广播给当前站点组下所有启用用户
    - target_type=selected：发送给 user_ids 列表中的用户

    提交后采用模式 B：返回列表片段 + OOB toast + 重置脚本（保留表单页继续推送）。
    """
    from app.core.exceptions import AppError
    from app.notifications import service as notif_service

    title = title.strip()
    content = content.strip()
    if not title or not content:
        raise AppError("标题和摘要不能为空", "invalid_input")

    # 解析目标用户 ID 列表
    if target_type == "all":
        target_ids = await notif_service.get_site_user_ids(
            db, site_group_id=tenant.site_group_id
        )
    else:
        # user_ids 来自多个同名 hidden input，FastAPI 解析为 list[int]
        target_ids = [int(uid) for uid in user_ids if uid]
        if not target_ids:
            raise AppError("请至少选择一个用户", "no_target_users")

    if not target_ids:
        raise AppError("未找到可推送的用户", "no_target_users")

    # 批量创建（广播）
    count = await notif_service.broadcast_notification(
        db,
        type=type,
        title=title,
        content=content,
        level=level,
        body=body.strip() if body else None,
        action_url=action_url.strip() if action_url else None,
        site_group_id=tenant.site_group_id,
        user_ids=target_ids,
    )
    await db.commit()

    # 模式 A：返回列表片段 + OOB toast（表单页被列表替换，相当于"回到列表页"）
    list_html = await _render_notifications_admin_list(db, tenant)
    toast = (
        '<div id="toast" hx-swap-oob="true" '
        'style="position:fixed;top:16px;right:16px;z-index:9999;'
        'background:#16a34a;color:#fff;padding:12px 16px;border-radius:8px;'
        'box-shadow:0 4px 12px rgba(0,0,0,0.15);font-size:14px;">'
        f'已成功推送给 {count} 个用户</div>'
    )
    return fragment_response(list_html + toast, request=request)


@router.delete("/notifications/{notification_id}")
async def admin_notification_delete(
    notification_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台删除单条站内信（admin 视角，按 site_group_id 校验归属）。"""
    from app.notifications import service as notif_service

    # admin 视角删除：不校验 user_id，但校验 site_group_id 归属
    from app.models.notification import Notification

    filters = [Notification.id == notification_id]
    if tenant.site_group_id:
        filters.append(
            (Notification.site_group_id == tenant.site_group_id)
            | (Notification.site_group_id.is_(None))
        )
    result = await db.execute(select(Notification).where(*filters))
    notif = result.scalar_one_or_none()
    if notif is None:
        raise NotFoundError("站内信不存在")
    await db.delete(notif)
    await db.commit()
    return await admin_notifications_list(request, db, tenant, user)
