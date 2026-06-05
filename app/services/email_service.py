"""
邮件发送服务

支持同步 SMTP 发送，可通过 run_in_executor 在异步上下文中使用。
"""
import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_smtp_config() -> dict:
    """从系统配置获取 SMTP 设置"""
    settings = get_settings()
    return {
        "host": settings.smtp_host,
        "port": settings.smtp_port,
        "username": settings.smtp_username,
        "password": settings.smtp_password,
        "from_email": settings.smtp_from_email,
        "use_tls": settings.smtp_use_tls,
    }


def _is_smtp_configured() -> bool:
    """检查 SMTP 是否已配置"""
    config = _get_smtp_config()
    return bool(config["host"] and config["username"] and config["password"] and config["from_email"])


def _send_email_sync(
    to: str | list[str],
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    from_email: Optional[str] = None,
) -> bool:
    """
    同步发送邮件

    Args:
        to: 收件人地址（单个或列表）
        subject: 邮件主题
        body: 纯文本正文
        html_body: HTML 正文（可选）
        from_email: 发件人地址（可选，默认使用系统配置）

    Returns:
        bool: 是否发送成功
    """
    config = _get_smtp_config()

    if not _is_smtp_configured():
        logger.warning("SMTP 未配置，无法发送邮件")
        return False

    if isinstance(to, str):
        to = [to]

    sender = from_email or config["from_email"]

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = ', '.join(to)
    msg['Subject'] = subject

    part_text = MIMEText(body, 'plain', 'utf-8')
    msg.attach(part_text)

    if html_body:
        part_html = MIMEText(html_body, 'html', 'utf-8')
        msg.attach(part_html)

    try:
        server = smtplib.SMTP(config["host"], config["port"])
        try:
            server.ehlo()

            if config["use_tls"]:
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()

            server.login(config["username"], config["password"])
            server.sendmail(sender, to, msg.as_string())
            logger.info("邮件发送成功: %s -> %s", subject, to)
            return True
        finally:
            try:
                server.quit()
            except smtplib.SMTPServerDisconnected:
                pass
    except Exception as e:
        logger.error("邮件发送失败: %s", str(e))
        return False


async def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    from_email: Optional[str] = None,
) -> bool:
    """
    异步发送邮件（在线程池中执行同步 SMTP 操作）

    Args:
        to: 收件人地址
        subject: 邮件主题
        body: 纯文本正文
        html_body: HTML 正文
        from_email: 发件人地址

    Returns:
        bool: 是否发送成功
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _send_email_sync,
        to,
        subject,
        body,
        html_body,
        from_email,
    )


def send_email_sync(
    to: str | list[str],
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    from_email: Optional[str] = None,
) -> bool:
    """
    同步发送邮件（Huey 任务使用）

    Args:
        to: 收件人地址
        subject: 邮件主题
        body: 纯文本正文
        html_body: HTML 正文
        from_email: 发件人地址

    Returns:
        bool: 是否发送成功
    """
    return _send_email_sync(to, subject, body, html_body, from_email)


async def send_verification_code(to: str, code: str) -> bool:
    """
    发送验证码邮件

    Args:
        to: 收件人地址
        code: 验证码

    Returns:
        bool: 是否发送成功
    """
    subject = "验证码 - 2c2a"
    body = f"您的验证码是: {code}\n\n验证码有效期为5分钟，请勿泄露给他人。"
    html_body = f"""
    <div style="max-width: 480px; margin: 0 auto; padding: 24px; font-family: sans-serif;">
        <h2 style="color: #333;">2c2a 验证码</h2>
        <p>您的验证码是：</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 4px;
                    color: #0066cc; padding: 12px 24px;
                    background: #f0f4ff; border-radius: 8px;
                    display: inline-block; margin: 8px 0;">
            {code}
        </div>
        <p style="color: #666; font-size: 14px;">
            验证码有效期为5分钟，请勿泄露给他人。
        </p>
    </div>
    """
    return await send_email(to, subject, body, html_body)


def send_verification_code_sync(to: str, code: str) -> bool:
    """
    同步发送验证码邮件（Huey 任务使用）

    Args:
        to: 收件人地址
        code: 验证码

    Returns:
        bool: 是否发送成功
    """
    subject = "验证码 - 2c2a"
    body = f"您的验证码是: {code}\n\n验证码有效期为5分钟，请勿泄露给他人。"
    return _send_email_sync(to, subject, body)
