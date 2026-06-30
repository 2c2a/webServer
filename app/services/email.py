"""异步邮件服务：基于 aiosmtplib 的全异步 SMTP 客户端。

设计要点：
- 全异步（铁律 #1）：使用 aiosmtplib，禁止同步 smtplib
- 租户隔离：SMTP 配置从 SystemConfig（全局）+ SiteGroupConfig（站点组覆盖）合并，
  站点组非空字段优先；密码字段使用字段级加密（smtp_password_cipher）
- 瞬时故障重试：连接拒绝/超时等可重试错误按指数退避重试
- 邮件正文：Jinja2 异步渲染（HTML + 纯文本双份，MIME multipart）
- 链接构造：密码重置链接基址可由配置显式指定，否则从请求 Host 头推导

使用方式：

    from app.services.email import send_password_reset_email, resolve_smtp_config

    cfg = await resolve_smtp_config(db, tenant)
    if cfg is None:
        # SMTP 未配置，回退 dev 行为（直接返回 token）
        ...
    else:
        await send_password_reset_email(cfg, to=user.email, reset_token=token,
                                         site_name="...", base_url="...")
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.tenant import SiteGroupConfig, SystemConfig
from app.security.field_cipher import decrypt_field
from app.templates import render_template
from app.tenant.resolver import TenantContext

log = get_logger(__name__)

# smtp_password_cipher 字段名（与模型注释一致，用于字段级解密）
_SMTP_PASSWORD_FIELD_SYSTEM = "system_config.smtp_password"
_SMTP_PASSWORD_FIELD_SITEGROUP = "site_group_config.smtp_password"

# 加密方式常量（与 SystemConfig.smtp_encryption 字段值一致）
ENCRYPTION_NONE = "NONE"        # 明文（仅限内网/邮件中继）
ENCRYPTION_STARTTLS = "STARTTLS"  # 显式 TLS（通常端口 587）
ENCRYPTION_SSL = "SSL"          # 隐式 TLS（通常端口 465）

# 可重试的瞬时异常类型（连接级故障；认证/拒绝类不重试）
_RETRYABLE_EXC = (
    asyncio.TimeoutError,
    ConnectionError,
    OSError,
    aiosmtplib.SMTPConnectError,
    aiosmtplib.SMTPServerDisconnected,
)


@dataclass
class SMTPConfig:
    """解析后的 SMTP 配置（密码已解密）。

    `is_configured` 为 False 时表示未配置 SMTP，调用方应走 dev fallback。
    """

    host: str = ""
    port: int = 587
    encryption: str = ENCRYPTION_STARTTLS
    username: str | None = None
    password: str | None = None
    from_email: str = ""
    from_name: str = ""

    @property
    def is_configured(self) -> bool:
        """是否已配置完整 SMTP（host + from_email 必填）。"""
        return bool(self.host and self.from_email)

    @property
    def use_tls(self) -> bool:
        """STARTTLS：True 表示先建明文连接再升级。"""
        return self.encryption.upper() == ENCRYPTION_STARTTLS

    @property
    def use_ssl(self) -> bool:
        """隐式 SSL：True 表示直接建立 TLS 连接。"""
        return self.encryption.upper() == ENCRYPTION_SSL

    @property
    def display_from(self) -> str:
        """格式化发件人地址（带显示名）。"""
        if self.from_name:
            return f"{self.from_name} <{self.from_email}>"
        return self.from_email


@dataclass
class SendResult:
    """邮件发送结果。"""

    success: bool
    error: str | None = None
    attempts: int = 0


# ──────────────────────────── 配置解析 ────────────────────────────


async def resolve_smtp_config(
    db: AsyncSession, tenant: TenantContext
) -> SMTPConfig | None:
    """解析生效的 SMTP 配置：站点组覆盖全局，密码字段解密。

    返回 None 表示环境禁用了邮件（settings.email_enabled=False）；
    返回 SMTPConfig 但 `is_configured=False` 表示未填写 host/from_email，
    调用方应走 dev fallback。
    """
    if not settings.email_enabled:
        return None

    # 全局 SystemConfig（单例 id=1）
    sys_result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
    sys_cfg = sys_result.scalar_one_or_none()

    # 站点组配置覆盖
    sg_cfg = None
    if tenant.site_group_id:
        sg_result = await db.execute(
            select(SiteGroupConfig).where(
                SiteGroupConfig.site_group_id == tenant.site_group_id
            )
        )
        sg_cfg = sg_result.scalar_one_or_none()

    cfg = SMTPConfig()

    # 全局默认
    if sys_cfg:
        cfg.host = sys_cfg.smtp_host or ""
        cfg.port = sys_cfg.smtp_port or 587
        cfg.encryption = (sys_cfg.smtp_encryption or ENCRYPTION_STARTTLS).upper()
        cfg.username = sys_cfg.smtp_username
        cfg.from_email = sys_cfg.smtp_from_email or ""
        cfg.from_name = sys_cfg.smtp_from_name or ""
        # 解密全局 SMTP 密码
        if sys_cfg.smtp_password_cipher:
            try:
                cfg.password = decrypt_field(
                    sys_cfg.smtp_password_cipher, _SMTP_PASSWORD_FIELD_SYSTEM
                )
            except ValueError as e:
                log.error("smtp_password_decrypt_failed_system", error=str(e))

    # 站点组覆盖（非空字段优先）
    if sg_cfg:
        if sg_cfg.smtp_host:
            cfg.host = sg_cfg.smtp_host
        if sg_cfg.smtp_port:
            cfg.port = sg_cfg.smtp_port
        if sg_cfg.smtp_encryption:
            cfg.encryption = sg_cfg.smtp_encryption.upper()
        if sg_cfg.smtp_username:
            cfg.username = sg_cfg.smtp_username
        if sg_cfg.smtp_from_email:
            cfg.from_email = sg_cfg.smtp_from_email
        if sg_cfg.smtp_from_name:
            cfg.from_name = sg_cfg.smtp_from_name
        # 站点组密码覆盖（独立字段名，避免与全局混淆）
        if sg_cfg.smtp_password_cipher:
            try:
                cfg.password = decrypt_field(
                    sg_cfg.smtp_password_cipher, _SMTP_PASSWORD_FIELD_SITEGROUP
                )
            except ValueError as e:
                log.error("smtp_password_decrypt_failed_sitegroup", error=str(e))

    return cfg


# ──────────────────────────── 核心发送 ────────────────────────────


async def send_email(
    cfg: SMTPConfig,
    *,
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> SendResult:
    """发送一封邮件（带瞬时故障重试）。

    Args:
        cfg: 已解析的 SMTP 配置（必须 is_configured=True）
        to: 收件人邮箱
        subject: 邮件主题
        html_body: HTML 正文
        text_body: 纯文本正文（可选，提供时构建 multipart）

    Returns:
        SendResult：成功/失败 + 错误描述 + 尝试次数
    """
    if not cfg.is_configured:
        return SendResult(success=False, error="SMTP 未配置完整（缺少 host 或 from_email）")

    msg = _build_message(
        cfg=cfg, to=to, subject=subject, html_body=html_body, text_body=text_body
    )

    max_attempts = max(1, settings.smtp_max_retries + 1)
    last_error: str | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            await _send_once(cfg, msg)
            log.info(
                "email_sent",
                to=to,
                subject=subject,
                host=cfg.host,
                port=cfg.port,
                attempt=attempt,
            )
            return SendResult(success=True, attempts=attempt)
        except _RETRYABLE_EXC as e:
            last_error = f"{type(e).__name__}: {e}"
            log.warning(
                "email_send_attempt_failed",
                to=to,
                subject=subject,
                host=cfg.host,
                attempt=attempt,
                max_attempts=max_attempts,
                error=last_error,
            )
            if attempt < max_attempts:
                backoff = settings.smtp_retry_backoff_base_seconds * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)
        except Exception as e:  # noqa: BLE001 不可重试异常直接退出
            last_error = f"{type(e).__name__}: {e}"
            log.error(
                "email_send_failed_non_retryable",
                to=to,
                subject=subject,
                error=last_error,
            )
            return SendResult(success=False, error=last_error, attempts=attempt)

    log.error(
        "email_send_exhausted",
        to=to,
        subject=subject,
        attempts=max_attempts,
        error=last_error,
    )
    return SendResult(success=False, error=last_error, attempts=max_attempts)


async def _send_once(cfg: SMTPConfig, msg: EmailMessage) -> None:
    """单次发送：建立连接 → 登录 → 发送 → 关闭（连接不复用，简单可靠）。"""
    smtp = aiosmtplib.SMTP(
        hostname=cfg.host,
        port=cfg.port,
        use_tls=cfg.use_ssl,
        timeout=settings.smtp_timeout_seconds,
    )
    try:
        await smtp.connect()
        # 显式 STARTTLS（use_tls=False 时才需要升级）
        if cfg.use_tls and not cfg.use_ssl:
            await smtp.starttls()
        if cfg.username:
            await smtp.login(cfg.username, cfg.password or "")
        await smtp.send_message(msg)
    finally:
        with contextlib.suppress(Exception):
            await smtp.quit()


def _build_message(
    *,
    cfg: SMTPConfig,
    to: str,
    subject: str,
    html_body: str,
    text_body: str | None,
) -> EmailMessage:
    """构建 MIME 邮件（纯文本优先，HTML 备选）。"""
    msg = EmailMessage()
    msg["From"] = cfg.display_from
    msg["To"] = to
    msg["Subject"] = subject

    if text_body:
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")
    else:
        msg.set_content(html_body, subtype="html")

    return msg


# ──────────────────────────── 业务封装 ────────────────────────────


async def send_password_reset_email(
    cfg: SMTPConfig,
    *,
    to: str,
    reset_token: str,
    base_url: str,
    site_name: str = "2c2a",
    expires_in_seconds: int = 600,
) -> SendResult:
    """发送密码重置邮件。

    Args:
        cfg: 已解析的 SMTP 配置
        to: 收件人邮箱
        reset_token: 密码重置令牌（Ed25519 签名）
        base_url: 站点基址（用于拼接重置链接），如 https://example.com
        site_name: 站点名称（邮件展示）
        expires_in_seconds: 令牌有效期（秒），用于展示「链接 X 分钟后失效」
    """
    # 构造重置链接：<base_url><path>?token=<token>
    base = base_url.rstrip("/")
    path = settings.password_reset_link_path
    reset_link = f"{base}{path}?token={reset_token}"

    import datetime as _dt

    context = {
        "site_name": site_name,
        "reset_link": reset_link,
        "expires_in_minutes": max(1, expires_in_seconds // 60),
        "year": _dt.datetime.now().year,
    }

    html_body = await render_template("password_reset.html", **context)
    text_body = await render_template("password_reset.txt", **context)

    subject = f"【{site_name}】密码重置"
    return await send_email(
        cfg, to=to, subject=subject, html_body=html_body, text_body=text_body
    )


async def send_verification_email(
    cfg: SMTPConfig,
    *,
    to: str,
    code: str,
    site_name: str = "2c2a",
    expires_in_seconds: int = 600,
) -> SendResult:
    """发送注册邮箱验证码邮件。

    Args:
        cfg: 已解析的 SMTP 配置
        to: 收件人邮箱
        code: 6 位数字验证码
        site_name: 站点名称（邮件展示）
        expires_in_seconds: 验证码有效期（秒）
    """
    import datetime as _dt

    context = {
        "site_name": site_name,
        "code": code,
        "expires_in_minutes": max(1, expires_in_seconds // 60),
        "year": _dt.datetime.now().year,
    }

    html_body = await render_template("email_verification.html", **context)
    text_body = await render_template("email_verification.txt", **context)

    subject = f"【{site_name}】邮箱验证码"
    return await send_email(
        cfg, to=to, subject=subject, html_body=html_body, text_body=text_body
    )


async def send_test_email(
    cfg: SMTPConfig, *, to: str, site_name: str = "2c2a"
) -> SendResult:
    """发送测试邮件（用于 CLI `2c2a mail test`）。"""
    import datetime as _dt

    context = {
        "site_name": site_name,
        "smtp_host": cfg.host,
        "smtp_port": cfg.port,
        "smtp_encryption": cfg.encryption,
        "from_email": cfg.from_email,
        "sent_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "year": _dt.datetime.now().year,
    }

    html_body = await render_template("test.html", **context)
    text_body = await render_template("test.txt", **context)

    subject = f"【{site_name}】SMTP 测试邮件"
    return await send_email(
        cfg, to=to, subject=subject, html_body=html_body, text_body=text_body
    )


# ──────────────────────────── 连接测试 ────────────────────────────


async def test_smtp_connection(cfg: SMTPConfig) -> tuple[bool, str]:
    """测试 SMTP 连接是否可达（不发送邮件）。

    Returns:
        (success, message)
    """
    if not cfg.is_configured:
        return False, "SMTP 未配置完整（缺少 host 或 from_email）"

    smtp = aiosmtplib.SMTP(
        hostname=cfg.host,
        port=cfg.port,
        use_tls=cfg.use_ssl,
        timeout=settings.smtp_timeout_seconds,
    )
    try:
        await smtp.connect()
        if cfg.use_tls and not cfg.use_ssl:
            await smtp.starttls()
        if cfg.username:
            await smtp.login(cfg.username, cfg.password or "")
        return True, f"连接成功（{cfg.host}:{cfg.port}，{cfg.encryption}）"
    except Exception as e:  # noqa: BLE001
        return False, f"连接失败：{type(e).__name__}: {e}"
    finally:
        with contextlib.suppress(Exception):
            await smtp.quit()


def describe_config(cfg: SMTPConfig | None) -> dict[str, Any]:
    """生成 SMTP 配置的可读摘要（不泄露密码），供 CLI/管理后台展示。"""
    if cfg is None:
        return {"enabled": False, "configured": False, "reason": "邮件发送已全局禁用"}
    return {
        "enabled": True,
        "configured": cfg.is_configured,
        "host": cfg.host or "",
        "port": cfg.port,
        "encryption": cfg.encryption,
        "username": cfg.username or "",
        "from_email": cfg.from_email or "",
        "from_name": cfg.from_name or "",
        "has_password": bool(cfg.password),
    }
