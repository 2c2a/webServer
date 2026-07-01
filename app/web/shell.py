"""用户前台页面路由（.design 体系，TRAE Work 主题）。

页面源自 2c2a-frontend.design，继承 frontend_shell.html 布局（登录/注册为独立页）。
路由仅渲染租户级配置 + 页面占位内容，真实用户数据后续通过 HTMX 片段注入。

注意：新模板含占位用户内容（如「你好，张三」），暂不走 App Shell 边缘缓存，
避免跨用户共享。待后续将占位内容替换为 HTMX 片段后可恢复缓存。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from starlette.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.templates import render_template
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext, get_effective_config

router = APIRouter(tags=["shell"])


async def _shell_context(tenant: TenantContext, db: AsyncSession) -> dict:
    """构建前台渲染上下文（仅租户级配置，无用户状态）。"""
    cfg = await get_effective_config(db, tenant)
    return {
        "site_name": cfg.get("site_name") or "2c2a",
        "site_icon": cfg.get("site_icon"),
        "icp_number": cfg.get("icp_number"),
        "theme": "light",
        "enable_registration": cfg.get("enable_registration", False),
    }


async def _render(
    tenant: TenantContext, db: AsyncSession, template: str, **extra
) -> HTMLResponse:
    """直接渲染前台页面（不走 App Shell 缓存）。"""
    ctx = await _shell_context(tenant, db)
    ctx.update(extra)
    html = await render_template(template, **ctx)
    return HTMLResponse(content=html)


@router.get("/")
async def index_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """主页落地页（对齐 2c2a-homepage/pages/index.html 设计稿）。

    公开落地页，仅含租户级配置（site_name / icp_number / year），无用户状态依赖。
    独立模板，不继承 frontend_shell（自带顶栏 + Hero + 功能卡片 + Footer）。
    """
    from datetime import datetime

    ctx = await _shell_context(tenant, db)
    ctx["year"] = str(datetime.now().year)
    html = await render_template("homepage.html", **ctx)
    return HTMLResponse(content=html)


@router.get("/dashboard")
async def dashboard_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """仪表盘。"""
    return await _render(tenant, db, "dashboard.html")


@router.get("/login")
async def login_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """登录页（独立模板，无导航）。"""
    return await _render(tenant, db, "login.html")


@router.get("/register")
async def register_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """注册页（独立模板，无导航）。"""
    return await _render(tenant, db, "register.html")


@router.get("/forgot-password")
async def forgot_password_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """忘记密码页（独立模板，无导航）。

    自助重置流程：用户名 + 注册邮箱 + 行为验证码 → 签发短期重置令牌 → 设置新密码。
    SMTP 已配置时通过邮件发送重置链接，未配置时直接返回 token（dev 回退）。
    """
    return await _render(tenant, db, "forgot_password.html")


@router.get("/reset-password")
async def reset_password_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """设置新密码页（独立模板，无导航）。

    邮件链接跳转目标：从 URL 查询参数 ``?token=...`` 读取重置令牌，
    提交后调用 ``/auth/reset-password`` 设置新密码。
    无 token 或 token 无效时显示错误提示。
    """
    return await _render(tenant, db, "reset_password.html")


@router.get("/cloud-computers")
async def cloud_computers_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """云电脑列表。"""
    return await _render(tenant, db, "cloud_computers.html")


@router.get("/cloud-computers/apply")
async def cloud_computer_apply_page(
    request: Request,
    product_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """云电脑申请。product_id 用于从产品列表跳转时预选产品。"""
    return await _render(tenant, db, "cloud_computer_apply.html", product_id=product_id)


@router.get("/my-cloud")
async def my_cloud_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """我的云电脑列表页（运行中 + 申请中合并）。"""
    return await _render(tenant, db, "my_cloud.html")


@router.get("/my-cloud/{cloud_user_id}")
async def my_cloud_detail_page(
    request: Request,
    cloud_user_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """我的云电脑详情页（运行中实例）。

    页面壳仅渲染占位容器，详情内容通过 HTMX 片段加载，便于「查看密码」「重置密码」等动作无刷新更新。
    """
    return await _render(tenant, db, "cloud_detail.html", cloud_user_id=cloud_user_id)


@router.get("/my-cloud/requests/{request_id}")
async def my_cloud_request_detail_page(
    request: Request,
    request_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """我的云电脑详情页（开户申请中）。

    页面壳仅渲染占位容器，详情内容通过 HTMX 片段加载，便于「重新申请」等动作无刷新更新。
    """
    return await _render(tenant, db, "cloud_detail.html", request_id=request_id)


@router.get("/tickets")
async def tickets_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """工单列表。"""
    return await _render(tenant, db, "tickets.html")


@router.get("/tickets/{ticket_id}")
async def ticket_detail_page(
    request: Request,
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """工单详情页（用户侧子页，对齐 2c2a-frontend/pages/ticket-detail.html 设计稿）。

    页面壳仅渲染占位容器，工单详情内容通过 HTMX 片段加载，便于回复后无刷新更新。
    """
    return await _render(tenant, db, "ticket_detail.html", ticket_id=ticket_id)


@router.get("/tickets/new")
async def submit_ticket_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """提交工单。"""
    return await _render(tenant, db, "submit_ticket.html")


@router.get("/points")
async def points_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """积分中心。"""
    return await _render(tenant, db, "points.html")


@router.get("/profile")
async def profile_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """个人中心。"""
    return await _render(tenant, db, "profile.html")


@router.get("/profile/change-password")
async def change_password_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """修改密码。"""
    return await _render(tenant, db, "change_password.html")


@router.get("/profile/email-manage")
async def email_manage_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """邮箱管理（对齐 2c2a-frontend/pages/email-manage.html 设计稿）。

    页面壳仅渲染占位容器，邮箱列表通过 HTMX 片段加载，便于增删/设为主邮箱后无刷新更新。
    """
    return await _render(tenant, db, "email_manage.html")


@router.get("/about")
async def about_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """关于我们（对齐 2c2a-frontend/pages/about.html 设计稿）。

    使用租户级配置（site_name / icp_number）渲染静态信息，无用户状态依赖。
    """
    from datetime import datetime

    ctx = await _shell_context(tenant, db)
    ctx["year"] = str(datetime.now().year)
    html = await render_template("about.html", **ctx)
    return HTMLResponse(content=html)


@router.get("/notifications")
async def notifications_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """站内信页面（对齐 2c2a-frontend/pages/notifications.html 设计稿）。

    页面壳仅渲染顶栏 + 过滤标签 + 列表占位容器，列表内容通过 HTMX 加载。
    含用户状态（顶栏铃铛未读角标），不走 App Shell 缓存。
    """
    from app.notifications.types import FILTER_TABS

    ctx = await _shell_context(tenant, db)
    ctx["filter_tabs"] = FILTER_TABS
    ctx["current_filter"] = "all"
    html = await render_template("notifications.html", **ctx)
    return HTMLResponse(content=html)
