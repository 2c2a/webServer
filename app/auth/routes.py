"""认证路由：登录、注册、刷新、登出。

- 登录：验证 BLAKE2b 预哈希 + Argon2id，签发 Ed25519 JWT（内存）+ AES-GCM Refresh（Cookie）
- 刷新：用 Refresh Token 换取新 Access Token（滑动窗口）
- 登出：清除 Refresh Cookie（前端清除内存 Access Token）
- 注册：BLAKE2b 预哈希 + Argon2id 存储
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SendEmailCodeRequest,
    SendEmailCodeResponse,
    UserInfo,
)
from app.captcha.dependencies import assert_captcha_solved
from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import AppError, AuthError, ForbiddenError, RateLimitError
from app.core.logging import get_logger
from app.models.user import User, UserProfile
from app.security.jwt_auth import (
    PASSWORD_RESET_TOKEN_TTL,
    decode_password_reset_token,
    issue_access_token,
    issue_password_reset_token,
)
from app.security.password import hash_password, needs_rehash, verify_password
from app.security.refresh_token import (
    clear_refresh_cookie,
    decode_refresh_token,
    issue_refresh_token,
    set_refresh_cookie,
)
from app.tenant.dependencies import get_client_ip, get_tenant
from app.tenant.resolver import TenantContext, get_effective_config

log = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """用户登录。

    前端先对密码做 BLAKE2b 预哈希（防 DoS），后端 Argon2id 验证。
    成功后签发 Ed25519 JWT（5 分钟，前端内存）+ AES-GCM Refresh（7 天，HttpOnly Cookie）。
    """
    ip = get_client_ip(request)
    # TODO: 速率限制（基于 Redis）

    # 行为验证码校验（按场景配置：login）
    await assert_captcha_solved(body.captcha_id, body.captcha, scene="login")

    result = await db.execute(
        select(User).options(selectinload(User.active_ban)).where(User.username == body.username)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password_prehash, user.password_hash):
        log.info("login_failed", username=body.username, ip=ip)
        raise AuthError("用户名或密码错误")

    if not user.is_active:
        raise AuthError("账号已被禁用")

    # 检查封禁
    if user.active_ban is not None:
        raise AuthError("账号已被封禁")

    # Argon2id 参数升级时重新哈希
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password_prehash)
        await db.commit()

    # 签发令牌
    access_token = issue_access_token(
        user_id=user.id,
        username=user.username,
        ban_version=user.ban_version,
        site_group_id=tenant.site_group_id,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
    )
    refresh_token = issue_refresh_token(
        user_id=user.id,
        ban_version=user.ban_version,
        site_group_id=tenant.site_group_id,
    )
    set_refresh_cookie(response, refresh_token)

    log.info("login_success", user_id=user.id, username=user.username, ip=ip)
    return LoginResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        username=user.username,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
    )


@router.post("/register", response_model=LoginResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """用户注册。

    注册要求：
    - 用户名、邮箱、密码（BLAKE2b 预哈希）+ 邮箱验证码 + 行为验证码
    - 行为验证码（scene='register'）由前端在点击注册按钮后弹出，
      通过后才能调用本端点
    - 邮箱验证码需先调用 ``/auth/send-email-code`` 获取
    - 邮箱验证码校验通过后一次性消费
    """
    # 检查注册是否开启（站点组配置覆盖全局配置）
    cfg = await get_effective_config(db, tenant)
    if not cfg.get("enable_registration", False):
        raise ForbiddenError("注册功能已关闭")

    # 行为验证码校验（按场景配置：register）
    await assert_captcha_solved(body.captcha_id, body.captcha, scene="register")

    # 邮箱验证码校验（一次性消费）
    from app.services.email_code import verify_code as verify_email_code

    if not await verify_email_code(body.email, body.email_code):
        raise AppError("邮箱验证码无效或已过期", "email_code_invalid", 400)

    # 检查用户名是否已存在
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise AppError("用户名已存在", "username_exists")

    # 检查邮箱是否已被注册
    existing_email = await db.execute(select(User).where(User.email == body.email))
    if existing_email.scalar_one_or_none() is not None:
        raise AppError("该邮箱已被注册", "email_exists")

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password_prehash),
        is_active=True,
        is_verified=True,  # 邮箱已验证
    )
    db.add(user)
    await db.flush()
    # 创建空 profile
    db.add(UserProfile(user_id=user.id))
    await db.commit()

    access_token = issue_access_token(
        user_id=user.id,
        username=user.username,
        ban_version=user.ban_version,
        site_group_id=tenant.site_group_id,
    )
    refresh_token = issue_refresh_token(
        user_id=user.id, ban_version=user.ban_version, site_group_id=tenant.site_group_id
    )
    set_refresh_cookie(response, refresh_token)

    log.info("register_success", user_id=user.id, username=user.username, email=body.email)
    return LoginResponse(
        access_token=access_token,
        expires_in=settings.access_token_ttl_seconds,
        username=user.username,
        is_superuser=False,
        is_staff=False,
    )


@router.post("/send-email-code", response_model=SendEmailCodeResponse)
async def send_email_code(
    body: SendEmailCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """发送注册邮箱验证码。

    流程：
    1. 前端先弹出行为验证码（scene='email'），用户通过验证
    2. 提交邮箱 + captcha_id 调用本端点
    3. 后端二次校验行为验证码（一次性消费）
    4. 频率限制：同一邮箱 60 秒内只能发送一次
    5. SMTP 已配置：发送 6 位数字验证码邮件，返回 ``sent=True``
    6. SMTP 未配置（dev/demo）：直接返回 ``dev_code`` 供前端填入

    返回值：
    - ``sent=True`` + ``expires_in``：邮件已发送
    - ``sent=False`` + ``resend_in>0``：频率限制中
    - ``sent=False`` + ``dev_code``：dev 回退（SMTP 未配置）
    """
    ip = get_client_ip(request)

    # 行为验证码二次校验（scene='email'）
    await assert_captcha_solved(body.captcha_id, body.captcha, scene="email")

    # 检查邮箱是否已被注册（不阻止发送，但前端给出提示更友好）
    # 此处仅检查，不抛错，防止通过此接口枚举邮箱

    from app.services.email_code import try_issue
    from app.services.email import resolve_smtp_config, send_verification_email

    # 生成验证码（带频率限制）
    result = await try_issue(body.email)
    if not result.success:
        # 频率限制中
        log.info(
            "send_email_code_rate_limited",
            email=body.email,
            ip=ip,
            resend_in=result.resend_in,
        )
        return SendEmailCodeResponse(
            sent=False, expires_in=result.ttl, resend_in=result.resend_in
        )

    # SMTP 已配置：发送邮件
    smtp_cfg = await resolve_smtp_config(db, tenant)
    if smtp_cfg is not None and smtp_cfg.is_configured:
        cfg = await get_effective_config(db, tenant)
        site_name = cfg.get("site_name") or settings.app_name

        send_result = await send_verification_email(
            smtp_cfg,  # type: ignore[arg-type]
            to=body.email,
            code=result.code,  # type: ignore[arg-type]
            site_name=site_name,
            expires_in_seconds=result.ttl,
        )

        if send_result.success:
            log.info(
                "send_email_code_sent",
                email=body.email,
                ip=ip,
                attempts=send_result.attempts,
            )
            return SendEmailCodeResponse(sent=True, expires_in=result.ttl)

        # 发送失败：回退到 dev_code（仅 dev/demo 模式）
        log.error(
            "send_email_code_failed",
            email=body.email,
            ip=ip,
            error=send_result.error,
        )
        if settings.debug or settings.demo:
            # demo/debug 模式：返回验证码以便演示流程继续，同时日志 warning 输出
            log.warning(
                "demo_email_code_revealed",
                email=body.email,
                code=result.code,
                ttl=result.ttl,
                mode="demo" if settings.demo else "debug",
            )
            return SendEmailCodeResponse(
                sent=False, expires_in=result.ttl, dev_code=result.code
            )
        # 生产模式不返回 code，前端提示稍后重试
        return SendEmailCodeResponse(
            sent=False, expires_in=result.ttl, resend_in=result.resend_in
        )

    # SMTP 未配置（dev/demo 回退）：直接返回 code
    log.info("send_email_code_dev", email=body.email, ip=ip)
    return SendEmailCodeResponse(
        sent=False, expires_in=result.ttl, dev_code=result.code
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """用 Refresh Token 换取新 Access Token（滑动窗口轮换）。"""
    cookie_token = request.cookies.get(settings.refresh_token_cookie_name, "")
    payload = decode_refresh_token(cookie_token)
    if payload is None:
        raise AuthError("Refresh Token 无效或已过期")

    user_id = int(payload["sub"])
    jwt_bv = int(payload.get("bv", 0))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        clear_refresh_cookie(response)
        raise AuthError("用户不存在或已禁用")

    # ban_version 校验
    from app.security.ban_version import is_token_revoked

    if is_token_revoked(jwt_bv, user.ban_version):
        clear_refresh_cookie(response)
        raise AuthError("令牌已撤销，请重新登录")

    # 签发新 Access Token
    access_token = issue_access_token(
        user_id=user.id,
        username=user.username,
        ban_version=user.ban_version,
        site_group_id=payload.get("sg"),
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
    )
    # 轮换 Refresh Token（滑动窗口）
    new_refresh = issue_refresh_token(
        user_id=user.id,
        ban_version=user.ban_version,
        site_group_id=payload.get("sg"),
    )
    set_refresh_cookie(response, new_refresh)

    return RefreshResponse(access_token=access_token, expires_in=settings.access_token_ttl_seconds)


@router.post("/logout")
async def logout(response: Response):
    """登出：清除 Refresh Cookie（前端清除内存 Access Token）。"""
    clear_refresh_cookie(response)
    return {"success": True}


@router.get("/me", response_model=UserInfo)
async def me(user=Depends(get_current_user)):
    """获取当前用户信息。"""
    return UserInfo(
        id=user.id,
        username=user.username,
        email=user.db_user.email if user.db_user else None,
        is_superuser=user.is_superuser,
        is_staff=user.is_staff,
        is_verified=user.db_user.is_verified if user.db_user else False,
    )


@router.post("/password")
async def change_password(
    body: ChangePasswordRequest,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改密码。"""
    if user.db_user is None:
        raise AuthError()
    if not verify_password(body.old_password_prehash, user.db_user.password_hash):
        raise AuthError("原密码错误")
    user.db_user.password_hash = hash_password(body.new_password_prehash)
    # 递增 ban_version 使所有已签发令牌失效（无状态撤销）
    user.db_user.ban_version += 1
    await db.commit()
    return {"success": True}


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """忘记密码 - 自助重置第一步。

    校验用户名 + 注册邮箱 + 行为验证码（复用 login 场景配置）。
    全部通过后签发短期密码重置令牌（Ed25519 签名，10 分钟有效）。

    分两种响应模式：
    - SMTP 已配置：向邮箱发送含重置链接的邮件，返回 ``email_sent=True``
      （不泄漏邮箱是否匹配，防止账号枚举；邮件发送失败时回退返回 token）
    - SMTP 未配置（dev/demo 回退）：直接返回 ``reset_token``，前端凭令牌
      调用 ``/auth/reset-password`` 设置新密码

    安全设计：
    - 邮箱必须与账号绑定的邮箱完全匹配（区分大小写不敏感）
    - 验证码一次性消费，防止自动化撞库
    - 令牌携带 ban_version，封禁期间令牌自动失效
    - 不签发登录态令牌，重置后仍需用新密码登录
    """
    from app.services.email import resolve_smtp_config, send_password_reset_email
    from app.tenant.resolver import get_effective_config

    ip = get_client_ip(request)
    # TODO: 速率限制（基于 Redis），防止邮箱匹配枚举

    # 行为验证码校验（复用 login 场景配置）
    await assert_captcha_solved(body.captcha_id, body.captcha, scene="login")

    result = await db.execute(
        select(User).options(selectinload(User.active_ban)).where(User.username == body.username)
    )
    user = result.scalar_one_or_none()

    # 校验失败：SMTP 模式下不泄漏具体原因，返回通用「邮件已发送」
    # dev 模式（未配置 SMTP）仍返回具体错误以便用户排查
    mismatch = (
        user is None
        or not user.is_active
        or user.active_ban is not None
        or not user.email
        or user.email.lower() != body.email.lower()
    )

    # 预解析 SMTP 配置，决定走哪种响应模式
    smtp_cfg = await resolve_smtp_config(db, tenant)
    use_email_flow = smtp_cfg is not None and smtp_cfg.is_configured

    if mismatch:
        # 失败日志（带原因，便于审计）
        reason = (
            "user_not_found" if user is None
            else "account_disabled" if not user.is_active
            else "account_banned" if user.active_ban is not None
            else "email_mismatch"
        )
        log.info(
            "forgot_password_mismatch",
            username=body.username,
            ip=ip,
            reason=reason,
            email_flow=use_email_flow,
        )
        if use_email_flow:
            # SMTP 模式：返回通用成功，防止账号枚举
            return ForgotPasswordResponse(
                email_sent=True, expires_in=PASSWORD_RESET_TOKEN_TTL
            )
        # dev 模式：返回具体错误
        if user is None or not user.email or user.email.lower() != body.email.lower():
            raise AppError("用户名或邮箱不匹配", "forgot_password_mismatch", 400)
        if not user.is_active:
            raise AuthError("账号已被禁用")
        if user.active_ban is not None:
            raise AuthError("账号已被封禁")
        # 兜底
        raise AppError("用户名或邮箱不匹配", "forgot_password_mismatch", 400)

    # 校验通过：签发短期重置令牌
    reset_token = issue_password_reset_token(
        user_id=user.id, ban_version=user.ban_version
    )

    if not use_email_flow:
        # SMTP 未配置（dev/demo 回退）：直接返回 token
        log.info(
            "forgot_password_issued_dev",
            user_id=user.id,
            username=user.username,
            ip=ip,
        )
        return ForgotPasswordResponse(
            email_sent=False, reset_token=reset_token, expires_in=PASSWORD_RESET_TOKEN_TTL
        )

    # SMTP 已配置：发送密码重置邮件
    # 推导 base_url：优先显式配置，否则用请求 Host 头
    base_url = settings.password_reset_link_base_url
    if not base_url:
        scheme = request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
        base_url = f"{scheme}://{host}" if host else ""

    cfg = await get_effective_config(db, tenant)
    site_name = cfg.get("site_name") or settings.app_name

    send_result = await send_password_reset_email(
        smtp_cfg,  # type: ignore[arg-type]
        to=user.email,  # type: ignore[arg-type]
        reset_token=reset_token,
        base_url=base_url,
        site_name=site_name,
        expires_in_seconds=PASSWORD_RESET_TOKEN_TTL,
    )

    if send_result.success:
        log.info(
            "forgot_password_email_sent",
            user_id=user.id,
            username=user.username,
            ip=ip,
            attempts=send_result.attempts,
        )
        return ForgotPasswordResponse(
            email_sent=True, expires_in=PASSWORD_RESET_TOKEN_TTL
        )

    # 邮件发送失败：回退返回 token（开发期便于排查，生产应告警）
    log.error(
        "forgot_password_email_failed",
        user_id=user.id,
        username=user.username,
        ip=ip,
        error=send_result.error,
        attempts=send_result.attempts,
    )
    # 不向前端泄漏失败原因，仅回退到 dev 行为
    return ForgotPasswordResponse(
        email_sent=False, reset_token=reset_token, expires_in=PASSWORD_RESET_TOKEN_TTL
    )


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """忘记密码 - 自助重置第二步。

    凭 ``/auth/forgot-password`` 签发的重置令牌设置新密码。
    校验令牌签名、用途、过期、ban_version 一致性后，写入新 Argon2id 哈希并递增 ban_version。
    """
    ip = get_client_ip(request)
    payload = decode_password_reset_token(body.reset_token)
    if payload is None:
        raise AuthError("重置链接无效或已过期")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise AuthError("重置链接无效")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthError("用户不存在")

    if not user.is_active:
        raise AuthError("账号已被禁用")

    # ban_version 校验：封禁/改密码后令牌立即失效
    token_bv = int(payload.get("bv", 0))
    from app.security.ban_version import is_token_revoked

    if is_token_revoked(token_bv, user.ban_version):
        raise AuthError("重置链接已失效，请重新申请")

    # 写入新密码并递增 ban_version（无状态撤销所有旧令牌）
    user.password_hash = hash_password(body.new_password_prehash)
    user.ban_version += 1
    await db.commit()

    log.info("reset_password_success", user_id=user.id, username=user.username, ip=ip)
    return {"success": True}
