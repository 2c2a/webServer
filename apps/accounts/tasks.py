from celery import shared_task
import logging

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_email_task(
    self,
    to_emails,
    subject,
    text_body,
    html_body=None,
    from_email=None,
):
    """
    异步发送邮件任务

    Args:
        to_emails: 收件人列表
        subject: 邮件主题
        text_body: 纯文本内容
        html_body: HTML 内容（可选）
        from_email: 发件人（可选，默认使用系统配置）
    """
    from apps.accounts.email_service import EmailService
    from apps.dashboard.models import SystemConfig

    try:
        config = SystemConfig.get_config()
        email_service = EmailService.from_system_config(config)
        email_service.send_email(
            to_emails=to_emails,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            from_email=from_email,
        )
    except Exception as exc:
        logger.error(f'异步邮件发送失败: {exc}', exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_ticket_email_task(
    self,
    subject,
    template_name,
    context,
    recipient_list,
):
    """
    异步发送工单邮件任务

    Args:
        subject: 邮件主题
        template_name: 邮件模板名称
        context: 模板上下文
        recipient_list: 收件人列表
    """
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from apps.accounts.email_service import EmailService
    from apps.dashboard.models import SystemConfig

    if not recipient_list:
        return

    try:
        html_message = render_to_string(template_name, context)
        plain_message = strip_tags(html_message)

        config = SystemConfig.get_config()
        from_email = (
            config.smtp_from_email
            if config and config.smtp_from_email
            else 'noreply@2c2a.com'
        )

        if config:
            try:
                email_service = EmailService.from_system_config(config)
                email_service.send_email(
                    to_emails=recipient_list,
                    subject=subject,
                    text_body=plain_message,
                    html_body=html_message,
                    from_email=from_email,
                )
                return
            except Exception:
                pass

        # 回退到 Django 的 send_mail
        from django.core.mail import send_mail
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=from_email,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=True,
        )
    except Exception as exc:
        logger.error(f'异步工单邮件发送失败: {exc}', exc_info=True)
        raise self.retry(exc=exc)
