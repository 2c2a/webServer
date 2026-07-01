"""后台管理详情/表单 HTMX 片段（不可缓存、仅 staff/superuser）。

负责详情/表单页相关动态片段：
- 用户详情 / 用户表单 / 用户创建 / 用户更新
- 开户审核 / 开户审核通过/拒绝 / 开户重试
- 积分任务表单 / 积分任务创建 / 积分任务更新
- 站点组表单 / 站点组创建 / 站点组更新

主机表单 / 工单详情 / 产品表单复用 admin_fragments.py 中现有路由。
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.responses import HTMLResponse

from app.auth.dependencies import require_staff, require_superuser
from app.cache.fragments import fragment_response
from app.core.db import get_db
from app.core.exceptions import AppError, NotFoundError
from app.models.operations import AccountOpeningRequest
from app.models.points import PointTask
from app.models.tenant import SiteGroup
from app.models.user import User, UserProfile
from app.points.registry import point_detector_registry
from app.security.password import hash_password
from app.templates import render_template
from app.tenant.dependencies import get_tenant, reject_demo
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/fragments/admin", tags=["admin-detail-fragments"])


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
# 用户管理
# ──────────────────────────────────────────────


@router.get("/users/detail")
async def admin_users_detail(
    request: Request,
    user_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台用户详情片段。"""
    uid = _parse_int_or_none(user_id)
    if not uid:
        raise NotFoundError("用户不存在")
    query = (
        select(User)
        .where(User.id == uid)
        .options(
            selectinload(User.profile),
            selectinload(User.site_groups),
            selectinload(User.admin_site_groups),
            selectinload(User.active_ban),
        )
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundError("用户不存在")
    html = await render_template("admin/users_detail.html", item=item)
    return fragment_response(html, request=request)


@router.get("/users/form")
async def admin_users_form(
    request: Request,
    user_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台用户创建/编辑表单片段。"""
    uid = _parse_int_or_none(user_id)
    item = None
    if uid:
        query = (
            select(User)
            .where(User.id == uid)
            .options(selectinload(User.site_groups))
        )
        result = await db.execute(query)
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundError("用户不存在")
    html = await render_template("admin/users_form.html", item=item)
    return fragment_response(html, request=request)


def _blake2b_prehash(plaintext: str) -> str:
    """对明文密码做 BLAKE2b 预哈希（模拟前端流程，与登录链路兼容）。"""
    return hashlib.blake2b(plaintext.encode(), digest_size=64).hexdigest()


async def _render_users_list(request: Request, db: AsyncSession) -> HTMLResponse:
    """查询全部用户并返回用户列表片段。"""
    result = await db.execute(select(User).order_by(User.id.desc()))
    items = result.scalars().all()
    html = await render_template("admin/users_list.html", items=items)
    return fragment_response(html, request=request)


@router.post("/users/create")
async def admin_users_create(
    request: Request,
    username: str = Form(),
    email: str = Form(),
    phone: str | None = Form(None),
    password: str = Form(),
    is_active: bool = Form(False),
    is_staff: bool = Form(False),
    is_superuser: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台创建用户并返回用户列表片段。

    表单提交明文密码，后端先做 BLAKE2b 预哈希（与前端流程一致），再 Argon2id 慢哈希。
    """
    # 仅超管可创建超管
    if is_superuser and not user.is_superuser:
        raise AppError("无权创建超级管理员", "forbidden")

    # 用户名唯一性校验
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        raise AppError("用户名已存在", "username_exists")

    new_user = User(
        username=username,
        email=email or None,
        phone=phone or None,
        password_hash=hash_password(_blake2b_prehash(password)),
        is_active=is_active,
        is_staff=is_staff,
        is_superuser=is_superuser,
        is_verified=False,
    )
    db.add(new_user)
    await db.flush()
    db.add(UserProfile(user_id=new_user.id))
    await db.commit()
    return await _render_users_list(request, db)


@router.put("/users/{user_id}")
async def admin_users_update(
    request: Request,
    user_id: int,
    email: str = Form(),
    phone: str | None = Form(None),
    password: str | None = Form(None),
    is_active: bool = Form(False),
    is_staff: bool = Form(False),
    is_superuser: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台更新用户并返回用户列表片段。

    - 修改密码时递增 ban_version（无状态撤销已签发令牌）
    - 普通管理员不能授予/撤销 superuser 身份
    """
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("用户不存在")

    # superuser 权限变更仅超管可操作
    if is_superuser != target.is_superuser and not user.is_superuser:
        raise AppError("无权修改超级管理员身份", "forbidden")

    target.email = email or None
    target.phone = phone or None
    target.is_active = is_active
    target.is_staff = is_staff
    target.is_superuser = is_superuser

    if password:
        # 明文 → BLAKE2b 预哈希 → Argon2id 慢哈希
        target.password_hash = hash_password(_blake2b_prehash(password))
        target.ban_version += 1  # 令所有已签发 token 失效

    await db.commit()
    return await _render_users_list(request, db)


@router.post("/users/{user_id}/toggle-ban")
async def admin_users_toggle_ban(
    request: Request,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台封禁/解封用户并返回用户列表片段。

    - 切换 is_active 状态；封禁时递增 ban_version（无状态撤销已签发令牌）
    - 不可封禁超级管理员；非超管不可封禁其他 staff
    """
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("用户不存在")

    # superuser 仅超管可操作；staff 仅超管可封禁
    if target.is_superuser and not user.is_superuser:
        raise AppError("无权封禁超级管理员", "forbidden")
    if target.is_staff and not user.is_superuser and target.id != user.id:
        raise AppError("无权封禁其他管理员", "forbidden")
    if target.id == user.id:
        raise AppError("不可封禁当前登录账号", "forbidden")

    target.is_active = not target.is_active
    if not target.is_active:
        target.ban_version += 1  # 封禁时令所有已签发 token 失效

    await db.commit()
    return await _render_users_list(request, db)


@router.post("/users/{user_id}/reset-password")
async def admin_users_reset_password(
    request: Request,
    user_id: int,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台重置用户密码并返回用户列表片段。

    - 表单提交明文密码，后端先做 BLAKE2b 预哈希（与前端流程一致），再 Argon2id 慢哈希
    - 重置后递增 ban_version（无状态撤销已签发令牌，强制用户使用新密码重新登录）
    - superuser 仅超管可重置
    """
    if not password or len(password) < 6:
        raise AppError("密码长度至少 6 位", "invalid_password")

    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("用户不存在")

    if target.is_superuser and not user.is_superuser:
        raise AppError("无权重置超级管理员密码", "forbidden")

    # 明文 → BLAKE2b 预哈希 → Argon2id 慢哈希
    target.password_hash = hash_password(_blake2b_prehash(password))
    target.ban_version += 1  # 令所有已签发 token 失效

    await db.commit()
    return await _render_users_list(request, db)


# ──────────────────────────────────────────────
# 开户审核
# ──────────────────────────────────────────────


@router.get("/openings/review")
async def admin_openings_review(
    request: Request,
    opening_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台开户申请审核详情片段。"""
    oid = _parse_int_or_none(opening_id)
    if not oid:
        raise NotFoundError("开户申请不存在")
    query = (
        select(AccountOpeningRequest)
        .where(AccountOpeningRequest.id == oid)
        .options(
            selectinload(AccountOpeningRequest.applicant),
            selectinload(AccountOpeningRequest.target_product),
            selectinload(AccountOpeningRequest.approved_by),
        )
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundError("开户申请不存在")
    html = await render_template("admin/openings_review.html", item=item)
    return fragment_response(html, request=request)


async def _render_openings_review(
    request: Request, db: AsyncSession, opening_id: int
) -> HTMLResponse:
    """重新查询开户申请并返回审核详情片段。"""
    query = (
        select(AccountOpeningRequest)
        .where(AccountOpeningRequest.id == opening_id)
        .options(
            selectinload(AccountOpeningRequest.applicant),
            selectinload(AccountOpeningRequest.target_product),
            selectinload(AccountOpeningRequest.approved_by),
        )
    )
    result = await db.execute(query)
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundError("开户申请不存在")
    html = await render_template("admin/openings_review.html", item=item)
    return fragment_response(html, request=request)


@router.post("/openings/{opening_id}/approve")
async def admin_openings_approve(
    request: Request,
    opening_id: int,
    action: str = Form(...),
    approval_notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台审核开户申请（通过/拒绝）并返回审核详情片段。

    - action=approve: 标记为 approved，异步触发 process_account_opening 创建云桌面
    - action=reject:  标记为 rejected
    """
    from app.tasks.operations import process_account_opening

    if action not in ("approve", "reject"):
        raise AppError("非法的审核操作", "invalid_action")

    result = await db.execute(
        select(AccountOpeningRequest).where(AccountOpeningRequest.id == opening_id)
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise NotFoundError("开户申请不存在")
    if req.status != "pending":
        raise AppError("仅待审核申请可执行此操作", "invalid_status")

    req.approved_by_id = user.id
    req.approval_date = datetime.now(timezone.utc)
    req.approval_notes = approval_notes or None

    if action == "approve":
        req.status = "approved"
        await db.commit()
        # 异步在远程主机创建用户（WinRM 长操作放后台任务）
        process_account_opening.schedule(args=(req.id,))
    else:
        req.status = "rejected"
        await db.commit()

    return await _render_openings_review(request, db, opening_id)


@router.post("/openings/{opening_id}/retry")
async def admin_openings_retry(
    request: Request,
    opening_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台重试失败的云桌面创建并返回审核详情片段。

    仅 status=failed 时可重试；递增 retry_count 后再次触发后台任务。
    """
    from app.tasks.operations import process_account_opening

    result = await db.execute(
        select(AccountOpeningRequest).where(AccountOpeningRequest.id == opening_id)
    )
    req = result.scalar_one_or_none()
    if req is None:
        raise NotFoundError("开户申请不存在")
    if req.status != "failed":
        raise AppError("仅创建失败的申请可重试", "invalid_status")

    req.status = "approved"
    req.retry_count = (req.retry_count or 0) + 1
    req.result_message = None
    await db.commit()

    process_account_opening.schedule(args=(req.id,))
    return await _render_openings_review(request, db, opening_id)


# ──────────────────────────────────────────────
# 积分任务
# ──────────────────────────────────────────────


@router.get("/points/tasks/form")
async def admin_points_tasks_form(
    request: Request,
    task_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_staff),
):
    """后台积分任务创建/编辑表单片段。"""
    tid = _parse_int_or_none(task_id)
    item = None
    if tid:
        query = select(PointTask).where(PointTask.id == tid)
        if tenant.site_group_id:
            query = query.where(
                (PointTask.site_group_id == tenant.site_group_id)
                | (PointTask.site_group_id.is_(None))
            )
        result = await db.execute(query)
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundError("积分任务不存在")
    html = await render_template("admin/points_tasks_form.html", item=item)
    return fragment_response(html, request=request)


def _parse_task_config(raw: str | None) -> dict | None:
    """解析积分任务 config 字段（JSON 字符串 → dict）。

    空字符串或纯空白返回 None；解析失败抛 AppError 提示前端。
    """
    if not raw or not raw.strip():
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AppError(f"配置 JSON 解析失败：{e.msg}", "invalid_config") from None
    if not isinstance(value, dict):
        raise AppError("配置必须是 JSON 对象", "invalid_config")
    return value


def _is_active_truthy(raw: str) -> bool:
    """表单 is_active 字段为 hidden input，值 'true'/'false' 字符串。"""
    return str(raw).strip().lower() in ("true", "1", "on", "yes")


async def _render_points_tasks(
    request: Request, db: AsyncSession, tenant: TenantContext
) -> HTMLResponse:
    """查询积分任务列表并返回列表片段。"""
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


@router.post("/points/tasks/create")
async def admin_points_tasks_create(
    request: Request,
    name: str = Form(),
    description: str | None = Form(None),
    detection_method: str = Form(),
    points: int = Form(0),
    is_active: str = Form("true"),
    config: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台创建积分任务并返回列表片段。

    detection_method 必须为已注册的检测方式（含插件注入）。
    """
    if point_detector_registry.get(detection_method) is None:
        raise NotFoundError(f"检测方式 {detection_method} 未注册")

    task = PointTask(
        name=name,
        description=description or None,
        detection_method=detection_method,
        points=points,
        is_active=_is_active_truthy(is_active),
        config=_parse_task_config(config),
        site_group_id=tenant.site_group_id,
        created_by_id=user.id,
    )
    db.add(task)
    await db.commit()
    return await _render_points_tasks(request, db, tenant)


@router.put("/points/tasks/{task_id}")
async def admin_points_tasks_update(
    request: Request,
    task_id: int,
    name: str = Form(),
    description: str | None = Form(None),
    detection_method: str = Form(),
    points: int = Form(0),
    is_active: str = Form("true"),
    config: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台更新积分任务并返回列表片段。"""
    query = select(PointTask).where(PointTask.id == task_id)
    if tenant.site_group_id:
        query = query.where(
            (PointTask.site_group_id == tenant.site_group_id)
            | (PointTask.site_group_id.is_(None))
        )
    result = await db.execute(query)
    task = result.scalar_one_or_none()
    if task is None:
        raise NotFoundError("积分任务不存在")

    if point_detector_registry.get(detection_method) is None:
        raise NotFoundError(f"检测方式 {detection_method} 未注册")

    task.name = name
    task.description = description or None
    task.detection_method = detection_method
    task.points = points
    task.is_active = _is_active_truthy(is_active)
    task.config = _parse_task_config(config)

    await db.commit()
    return await _render_points_tasks(request, db, tenant)


# ──────────────────────────────────────────────
# 积分手动调整（staff/superuser）
# ──────────────────────────────────────────────


@router.post("/points/adjust")
async def admin_points_adjust(
    request: Request,
    user_id: int = Form(...),
    delta: int = Form(...),
    description: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    user=Depends(require_staff),
):
    """后台手动调整用户积分。

    - delta > 0：调用 award_points（source=admin）；
    - delta < 0：调用 deduct_points（含余额校验，余额不足抛 ForbiddenError）；
    - delta == 0：直接拒绝。

    成功后刷新积分明细列表片段并返回成功 toast。
    """
    from app.points import service as points_service
    from app.models.points import PointRecord

    if delta == 0:
        raise AppError("变动数额不能为 0", "invalid_delta")

    target_result = await db.execute(select(User).where(User.id == user_id))
    target = target_result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("用户不存在")

    desc = (description or "").strip() or None
    if delta > 0:
        await points_service.award_points(
            db,
            user_id=user_id,
            delta=delta,
            source="admin",
            site_group_id=tenant.site_group_id,
            ref_type="admin",
            ref_id=user.id,
            description=desc or f"管理员手动发放 {delta} 积分",
        )
    else:
        await points_service.deduct_points(
            db,
            user_id=user_id,
            amount=-delta,
            site_group_id=tenant.site_group_id,
            ref_type="admin",
            ref_id=user.id,
            description=desc or f"管理员手动扣减 {-delta} 积分",
        )
    await db.commit()

    # 刷新积分明细列表片段（最近 100 条，租户过滤）
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
    list_html = await render_template("admin/points_records.html", items=items)

    # 成功 toast（OOB）+ 刷新后的列表 + 清空表单脚本
    toast = (
        '<div id="toast" hx-swap-oob="true" '
        'style="position:fixed;top:16px;right:16px;z-index:9999;'
        'background:#16a34a;color:#fff;padding:12px 16px;border-radius:8px;'
        'box-shadow:0 4px 12px rgba(0,0,0,0.15);font-size:14px;">'
        f'已为 {target.username} {"发放" if delta > 0 else "扣减"} {abs(delta)} 积分</div>'
    )
    reset_script = (
        '<script>/* reset-points-form */'
        'var f=document.getElementById("points-adjust-form");'
        'if(f){f.reset();}'
        'var chip=document.getElementById("selected-user-chip");'
        'if(chip){chip.style.display="none";}'
        'var hidden=document.getElementById("selected-user-id");'
        'if(hidden){hidden.value="";}'
        'var dropdown=document.getElementById("user-search-dropdown");'
        'if(dropdown){dropdown.innerHTML="";}'
        '</script>'
    )
    return fragment_response(list_html + toast + reset_script, request=request)


# ──────────────────────────────────────────────
# 站点组管理（仅超管）
# ──────────────────────────────────────────────


def _generate_slug(name: str) -> str:
    """根据名称生成 slug；非 ASCII 名称用随机串兜底。"""
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        slug = f"site-{secrets.token_hex(4)}"
    return slug


async def _render_sitegroups_list(request: Request, db: AsyncSession) -> HTMLResponse:
    """查询全部站点组并返回列表片段。"""
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


@router.get("/sitegroups/form")
async def admin_sitegroups_form(
    request: Request,
    site_group_id: str | int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_superuser),
    __=Depends(reject_demo),
):
    """后台站点组创建/编辑表单片段（仅超管，演示站点禁用）。"""
    sid = _parse_int_or_none(site_group_id)
    item = None
    if sid:
        result = await db.execute(select(SiteGroup).where(SiteGroup.id == sid))
        item = result.scalar_one_or_none()
        if item is None:
            raise NotFoundError("站点组不存在")
    html = await render_template("admin/sitegroups_form.html", item=item)
    return fragment_response(html, request=request)


@router.post("/sitegroups/create")
async def admin_sitegroups_create(
    request: Request,
    name: str = Form(),
    slug: str | None = Form(None),
    site_name: str | None = Form(None),
    site_icon: str | None = Form(None),
    description: str | None = Form(None),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_superuser),
    __=Depends(reject_demo),
):
    """后台创建站点组并返回列表片段（仅超管，演示站点禁用）。"""
    final_slug = (slug or "").strip() or _generate_slug(name)
    # slug 唯一性校验
    existing = await db.execute(select(SiteGroup).where(SiteGroup.slug == final_slug))
    if existing.scalar_one_or_none() is not None:
        raise AppError("Slug 已存在", "slug_exists")

    sg = SiteGroup(
        name=name.strip(),
        slug=final_slug,
        site_name=site_name or "",
        site_icon=site_icon or "",
        description=description or None,
        is_active=is_active,
    )
    db.add(sg)
    await db.commit()
    return await _render_sitegroups_list(request, db)


@router.put("/sitegroups/{site_group_id}")
async def admin_sitegroups_update(
    request: Request,
    site_group_id: int,
    name: str = Form(),
    site_name: str | None = Form(None),
    site_icon: str | None = Form(None),
    description: str | None = Form(None),
    is_active: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    _=Depends(require_superuser),
    __=Depends(reject_demo),
):
    """后台更新站点组并返回列表片段（仅超管，演示站点禁用）。"""
    result = await db.execute(select(SiteGroup).where(SiteGroup.id == site_group_id))
    sg = result.scalar_one_or_none()
    if sg is None:
        raise NotFoundError("站点组不存在")

    sg.name = name.strip()
    sg.site_name = site_name or ""
    sg.site_icon = site_icon or ""
    sg.description = description or None
    sg.is_active = is_active
    await db.commit()
    return await _render_sitegroups_list(request, db)
