"""后台管理列表页 HTMX 片段（不可缓存、仅 staff/superuser）。

包含概览 KPI、待处理工单、待审核开户、系统任务、用户、主机组、开户申请、
积分任务、积分明细、审计日志、站点组、系统配置、Huey 任务队列等列表片段。
所有片段均通过 fragment_response 返回，标记为 no-store。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import require_staff, require_superuser, CurrentUser
from app.cache.fragments import fragment_response
from app.core.db import get_db
from app.models.audit import AuditLog
from app.models.host import Host, HostGroup
from app.models.operations import (
    AccountOpeningRequest,
    CloudComputerUser,
    Product,
    ProductGroup,
    SystemTask,
)
from app.models.points import PointRecord, PointTask, UserPoints
from app.models.tenant import SiteGroup, SystemConfig
from app.models.ticket import Ticket
from app.models.user import User
from app.templates import render_template
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/fragments/admin", tags=["admin-list-fragments"])


# ──────────────────────────────────────────────
# 后台概览
# ──────────────────────────────────────────────


@router.get("/overview/kpis")
async def admin_overview_kpis(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台概览 KPI 片段：用户总数、工单总数、云电脑数、今日签到数。"""
    # 今日 0 点 UTC（按 UTC 计算今日签到）
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async def _count(stmt):
        try:
            res = await db.execute(stmt)
            return int(res.scalar() or 0)
        except Exception:  # noqa: BLE001
            return 0

    users_count = await _count(select(func.count(User.id)))
    tickets_count = await _count(select(func.count(Ticket.id)))
    cloud_users_count = await _count(select(func.count(CloudComputerUser.id)))
    checkin_count = await _count(
        select(func.count(PointRecord.id)).where(
            PointRecord.source == "task",
            PointRecord.created_at >= today_start,
        )
    )

    html = await render_template(
        "admin/overview_kpis.html",
        users_count=users_count,
        tickets_count=tickets_count,
        cloud_users_count=cloud_users_count,
        checkin_count=checkin_count,
    )
    return fragment_response(html, request=request)


@router.get("/overview/pending-tickets")
async def admin_overview_pending_tickets(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台概览待处理工单片段（最近 5 条 open/pending）。"""
    query = (
        select(Ticket)
        .options(selectinload(Ticket.creator))
        .where(Ticket.status.in_(["open", "pending"]))
        .order_by(Ticket.created_at.desc())
        .limit(5)
    )
    if tenant.site_group_id:
        query = query.where(
            (Ticket.site_group_id == tenant.site_group_id)
            | (Ticket.site_group_id.is_(None))
        )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/overview_pending_tickets.html", items=items)
    return fragment_response(html, request=request)


@router.get("/overview/pending-openings")
async def admin_overview_pending_openings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台概览待审核开户片段（最近 5 条 pending）。"""
    query = (
        select(AccountOpeningRequest)
        .options(
            selectinload(AccountOpeningRequest.applicant),
            selectinload(AccountOpeningRequest.target_product),
        )
        .where(AccountOpeningRequest.status == "pending")
        .order_by(AccountOpeningRequest.created_at.desc())
        .limit(5)
    )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/overview_pending_openings.html", items=items)
    return fragment_response(html, request=request)


@router.get("/overview/system-tasks")
async def admin_overview_system_tasks(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台概览系统任务片段（最近 5 条）。"""
    query = (
        select(SystemTask)
        .order_by(SystemTask.created_at.desc())
        .limit(5)
    )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/overview_system_tasks.html", items=items)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 用户管理
# ──────────────────────────────────────────────


@router.get("/users/list")
async def admin_users_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台用户列表片段（admin 看全部，User 无 site_group_id）。"""
    query = select(User).order_by(User.id.desc())
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/users_list.html", items=items)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 主机组管理
# ──────────────────────────────────────────────


@router.get("/host-groups/list")
async def admin_host_groups_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台主机组列表片段（租户过滤 + 预加载 site_group / hosts）。"""
    query = (
        select(HostGroup)
        .options(
            selectinload(HostGroup.site_group),
            selectinload(HostGroup.hosts),
        )
        .order_by(HostGroup.id.desc())
    )
    if tenant.site_group_id:
        query = query.where(
            (HostGroup.site_group_id == tenant.site_group_id)
            | (HostGroup.site_group_id.is_(None))
        )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/host_groups_list.html", items=items)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 开户申请
# ──────────────────────────────────────────────


@router.get("/openings/list")
async def admin_openings_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台开户申请列表片段（预加载 applicant / target_product / approved_by）。"""
    query = (
        select(AccountOpeningRequest)
        .options(
            selectinload(AccountOpeningRequest.applicant),
            selectinload(AccountOpeningRequest.target_product),
            selectinload(AccountOpeningRequest.approved_by),
        )
        .order_by(AccountOpeningRequest.created_at.desc())
    )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/openings_list.html", items=items)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 积分管理
# ──────────────────────────────────────────────


@router.get("/points/tasks")
async def admin_points_tasks(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台积分任务列表片段（租户过滤）。"""
    query = select(PointTask).order_by(PointTask.id.desc())
    if tenant.site_group_id:
        query = query.where(
            (PointTask.site_group_id == tenant.site_group_id)
            | (PointTask.site_group_id.is_(None))
        )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/points_tasks.html", items=items)
    return fragment_response(html, request=request)


@router.get("/points/records")
async def admin_points_records(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台积分明细列表片段（最近 100 条，租户过滤，预加载 user / task）。"""
    query = (
        select(PointRecord)
        .options(
            selectinload(PointRecord.user),
            selectinload(PointRecord.task),
        )
        .order_by(PointRecord.id.desc())
        .limit(100)
    )
    if tenant.site_group_id:
        query = query.where(
            (PointRecord.site_group_id == tenant.site_group_id)
            | (PointRecord.site_group_id.is_(None))
        )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/points_records.html", items=items)
    return fragment_response(html, request=request)


@router.get("/points/users/search")
async def admin_points_users_search(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台手动调整积分：按用户名搜索用户，返回下拉候选片段。

    最多返回 10 条匹配项（username ILIKE %q%），按 username 升序。
    """
    q = (q or "").strip()
    if not q:
        return fragment_response("", request=request)

    query = select(User).where(User.username.ilike(f"%{q}%")).order_by(User.username).limit(10)
    result = await db.execute(query)
    users = result.scalars().all()

    html = await render_template("admin/points_users_search.html", users=users)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 审计日志
# ──────────────────────────────────────────────


@router.get("/audit/logs")
async def admin_audit_logs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user: CurrentUser = Depends(require_staff),
):
    """后台审计日志列表片段（最近 50 条，租户过滤，预加载 user / host）。

    非超管且无 site_group_id 时返回空（where AuditLog.id == -1）。
    """
    query = (
        select(AuditLog)
        .options(
            selectinload(AuditLog.user),
            selectinload(AuditLog.host),
        )
        .order_by(AuditLog.timestamp.desc())
        .limit(50)
    )
    if user.is_superuser:
        # 超管看全部
        pass
    elif tenant.site_group_id:
        query = query.where(
            (AuditLog.site_group_id == tenant.site_group_id)
            | (AuditLog.site_group_id.is_(None))
        )
    else:
        # 非超管且无租户上下文 → 强制返回空
        query = query.where(AuditLog.id == -1)
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/audit_logs.html", items=items)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 站点组管理
# ──────────────────────────────────────────────


@router.get("/sitegroups/list")
async def admin_sitegroups_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_superuser),
):
    """后台站点组列表片段（仅超管可访问）。

    预加载 hostnames / members / admins 关系，避免异步会话关闭后访问懒加载
    关系触发 DetachedInstanceError（模板访问 sg.hostnames|length 等）。
    """
    query = (
        select(SiteGroup)
        .options(
            selectinload(SiteGroup.hostnames),
            selectinload(SiteGroup.members),
            selectinload(SiteGroup.admins),
        )
        .order_by(SiteGroup.id)
    )
    result = await db.execute(query)
    items = result.scalars().all()
    html = await render_template("admin/sitegroups_list.html", items=items)
    return fragment_response(html, request=request)


# ──────────────────────────────────────────────
# 系统配置
# ──────────────────────────────────────────────


@router.get("/settings/detail")
async def admin_settings_detail(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台系统配置详情片段（SystemConfig 单例 id=1）。

    首次访问时自动初始化默认记录，避免显示"系统配置尚未初始化"。
    """
    result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        config = SystemConfig(id=1)
        db.add(config)
        await db.commit()
    # 验证码类型列表（供下拉选择）
    from app.captcha.registry import captcha_registry
    captcha_types = captcha_registry.list_metadata()
    html = await render_template(
        "admin/settings_detail.html",
        config=config,
        captcha_types=captcha_types,
    )
    return fragment_response(html, request=request)


@router.post("/settings/captcha")
async def admin_settings_captcha_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_staff),
):
    """保存验证码场景配置（HTMX 表单提交）。

    字段（form-urlencoded）：
    - captcha_enabled (checkbox)
    - captcha_type (select)
    - captcha_required_on_login/register/email (checkbox)
    - login_captcha_type / register_captcha_type / email_captcha_type (select)
    """
    from app.captcha.scene_config import invalidate_captcha_config_cache

    form = await request.form()
    result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        config = SystemConfig(id=1)
        db.add(config)

    # checkbox 未勾选时不在 form 里
    config.captcha_enabled = "captcha_enabled" in form
    config.captcha_required_on_login = "captcha_required_on_login" in form
    config.captcha_required_on_register = "captcha_required_on_register" in form
    config.captcha_required_on_email = "captcha_required_on_email" in form
    # 类型字段：空字符串表示继承默认
    config.captcha_type = (form.get("captcha_type") or "").upper() or "SLIDER"
    config.login_captcha_type = (form.get("login_captcha_type") or "").upper() or None
    config.register_captcha_type = (form.get("register_captcha_type") or "").upper() or None
    config.email_captcha_type = (form.get("email_captcha_type") or "").upper() or None

    await db.commit()
    # 失效缓存
    invalidate_captcha_config_cache()

    return fragment_response(
        '<span style="color:var(--vercel-status-success);">✓ 已保存并立即生效</span>',
        request=request,
    )


@router.post("/settings/smtp")
async def admin_settings_smtp_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_staff),
):
    """保存 SMTP 配置（HTMX 表单提交）。

    字段（form-urlencoded）：
    - smtp_host / smtp_port / smtp_encryption / smtp_username / smtp_from_email / smtp_from_name
    - smtp_password：留空表示不修改（保留原密文）；非空则用字段级加密覆盖

    所有字段允许为空字符串（清空配置）；smtp_port 为空时存 NULL。
    """
    from app.security.field_cipher import encrypt_field

    form = await request.form()
    result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        config = SystemConfig(id=1)
        db.add(config)

    # 普通字段直接覆盖（空字符串 → None，便于后续 is_configured 判断）
    config.smtp_host = (form.get("smtp_host") or "").strip() or None
    config.smtp_username = (form.get("smtp_username") or "").strip() or None
    config.smtp_from_email = (form.get("smtp_from_email") or "").strip() or None
    config.smtp_from_name = (form.get("smtp_from_name") or "").strip() or None

    # 端口：空字符串 → NULL
    port_raw = (form.get("smtp_port") or "").strip()
    if port_raw:
        try:
            config.smtp_port = int(port_raw)
        except ValueError:
            config.smtp_port = None
    else:
        config.smtp_port = None

    # 加密方式：统一大写，空 → NULL（resolve 时回退默认 STARTTLS）
    enc = (form.get("smtp_encryption") or "").strip().upper()
    config.smtp_encryption = enc or None

    # 密码：留空不修改；非空则字段级加密
    password = form.get("smtp_password") or ""
    if password:
        config.smtp_password_cipher = encrypt_field(
            password, "system_config.smtp_password"
        )
    # 留空时保留原 smtp_password_cipher，不动

    await db.commit()

    return fragment_response(
        '<span style="color:var(--vercel-status-success);">✓ SMTP 配置已保存</span>',
        request=request,
    )


@router.post("/settings/registration")
async def admin_settings_registration_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_staff),
):
    """保存注册策略开关（HTMX 表单提交）。

    字段（form-urlencoded）：
    - enable_registration (checkbox)：未勾选视为关闭

    注册开关在 ``get_effective_config`` 中每次现取，不经过 Redis 缓存，
    故保存后立即生效，无需失效缓存。
    """
    form = await request.form()
    result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
    config = result.scalar_one_or_none()
    if config is None:
        config = SystemConfig(id=1)
        db.add(config)

    config.enable_registration = "enable_registration" in form

    await db.commit()

    return fragment_response(
        '<span style="color:var(--vercel-status-success);">✓ 注册策略已保存并立即生效</span>',
        request=request,
    )


@router.post("/settings/smtp/test")
async def admin_settings_smtp_test(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_staff),
):
    """测试 SMTP 连接是否可达（不发送邮件）。

    读取当前表单输入的配置（未保存也可测试），结合数据库已存密码：
    - 表单密码非空 → 用表单密码测试（用户正在改密码）
    - 表单密码为空 → 解密数据库已存密码测试

    这样用户填完主机/端口/账号/密码后无需先保存即可点「测试连接」。
    """
    from app.security.field_cipher import decrypt_field
    from app.services.email import SMTPConfig, test_smtp_connection

    form = await request.form()

    # 读取数据库现有配置（取已存密码）
    result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
    db_config = result.scalar_one_or_none()

    # 构造测试用 SMTPConfig：表单值优先，回退数据库值
    host = (form.get("smtp_host") or "").strip() or (
        db_config.smtp_host if db_config else ""
    )
    port_raw = (form.get("smtp_port") or "").strip()
    if port_raw:
        try:
            port = int(port_raw)
        except ValueError:
            port = 587
    else:
        port = db_config.smtp_port if db_config and db_config.smtp_port else 587

    enc = (form.get("smtp_encryption") or "").strip().upper()
    if not enc and db_config and db_config.smtp_encryption:
        enc = db_config.smtp_encryption.upper()
    if not enc:
        enc = "STARTTLS"

    username = (form.get("smtp_username") or "").strip() or (
        db_config.smtp_username if db_config else None
    )
    from_email = (form.get("smtp_from_email") or "").strip() or (
        db_config.smtp_from_email if db_config else ""
    )
    from_name = (form.get("smtp_from_name") or "").strip() or (
        db_config.smtp_from_name if db_config else ""
    )

    # 密码：表单非空用表单，否则解密数据库
    password = form.get("smtp_password") or ""
    if not password and db_config and db_config.smtp_password_cipher:
        try:
            password = decrypt_field(
                db_config.smtp_password_cipher, "system_config.smtp_password"
            )
        except ValueError:
            password = ""

    cfg = SMTPConfig(
        host=host,
        port=port,
        encryption=enc,
        username=username,
        password=password or None,
        from_email=from_email,
        from_name=from_name,
    )

    if not cfg.is_configured:
        return fragment_response(
            '<span style="color:var(--vercel-status-destructive);">'
            "✗ 未配置完整（缺少 SMTP 主机或发件邮箱）</span>",
            request=request,
        )

    ok, msg = await test_smtp_connection(cfg)
    if ok:
        return fragment_response(
            f'<span style="color:var(--vercel-status-success);">✓ {msg}</span>',
            request=request,
        )
    return fragment_response(
        f'<span style="color:var(--vercel-status-destructive);">✗ {msg}</span>',
        request=request,
    )


# ──────────────────────────────────────────────
# Huey 任务队列（只读）
# ──────────────────────────────────────────────


def _format_arg(value) -> str:
    """格式化任务参数值为字符串（截断长值）。"""
    try:
        s = repr(value)
    except Exception:  # noqa: BLE001
        s = "<unreprable>"
    if len(s) > 80:
        s = s[:77] + "..."
    return s


def _task_row(task) -> dict:
    """从 Huey Task 对象提取展示字段。"""
    args_str = ", ".join(_format_arg(a) for a in (task.args or ()))
    kwargs_str = ", ".join(f"{k}={_format_arg(v)}" for k, v in (task.kwargs or {}).items())
    params = args_str
    if kwargs_str:
        params = f"{params}, {kwargs_str}" if params else kwargs_str
    eta = None
    if task.eta:
        try:
            eta = task.eta.strftime("%Y-%m-%d %H:%M:%S")
        except (AttributeError, ValueError):
            eta = str(task.eta)
    return {
        "id": task.id,
        "name": task.name,
        "params": params or "—",
        "eta": eta,
        "retries": task.retries or 0,
        "priority": task.priority,
        "expires": task.expires,
    }


@router.get("/tasks/queue")
async def admin_tasks_queue(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台 Huey 任务队列只读片段。

    展示三类信息：
    - 待执行任务（pending，FIFO 队列中）
    - 调度任务（scheduled，带 eta 尚未到点）
    - 结果计数（result_count，已完成的任务结果数量）

    注意：Huey 的 ``pending()`` / ``scheduled()`` / ``all_results()`` 等方法
    均为同步阻塞调用（直接读 Redis），必须用 ``asyncio.to_thread`` 包装，
    否则违反铁律 #1（禁止同步阻塞调用出现在异步上下文）。

    Redis 不可用时优雅降级：返回空列表 + 错误提示。
    """
    from app.tasks.huey_app import huey

    error_msg: str | None = None
    pending_rows: list[dict] = []
    scheduled_rows: list[dict] = []
    pending_count = 0
    scheduled_count = 0
    result_count = 0

    try:
        # 用 asyncio.to_thread 包装同步阻塞的 Redis 读取
        pending_tasks, scheduled_tasks = await asyncio.gather(
            asyncio.to_thread(huey.pending),
            asyncio.to_thread(huey.scheduled),
        )
        pending_count, scheduled_count, result_count = await asyncio.gather(
            asyncio.to_thread(huey.pending_count),
            asyncio.to_thread(huey.scheduled_count),
            asyncio.to_thread(huey.result_count),
        )
        pending_rows = [_task_row(t) for t in pending_tasks]
        scheduled_rows = [_task_row(t) for t in scheduled_tasks]
    except Exception as exc:  # noqa: BLE001
        # Redis 不可用 / immediate 模式 / 反序列化失败等情况
        error_msg = f"无法读取任务队列：{exc}"

    html = await render_template(
        "admin/tasks_queue.html",
        pending_rows=pending_rows,
        scheduled_rows=scheduled_rows,
        pending_count=pending_count,
        scheduled_count=scheduled_count,
        result_count=result_count,
        error_msg=error_msg,
    )
    return fragment_response(html, request=request)

