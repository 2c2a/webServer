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


@shared_task(bind=True, max_retries=1, acks_late=True)
def send_test_email_task(self, async_task_id):
    """
    异步发送测试邮件，使用 AsyncTask 追踪状态

    Args:
        async_task_id: AsyncTask 记录的 PK
    """
    from apps.tasks.models import AsyncTask
    from apps.accounts.email_service import EmailService
    from apps.dashboard.models import SystemConfig

    try:
        task_record = AsyncTask.objects.get(pk=async_task_id)
    except AsyncTask.DoesNotExist:
        logger.error(f'AsyncTask {async_task_id} 不存在')
        return

    task_record.start_execution()

    try:
        config = SystemConfig.get_config()
        email_service = EmailService.from_system_config(config)
        test_email = (
            task_record.result.get('test_email', '')
            if task_record.result else ''
        )

        subject = '2c2a 测试邮件'
        from django.utils import timezone
        text_body = (
            f'这是一封测试邮件，用于验证邮件配置是否正确。'
            f'测试时间: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
        )
        html_body = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{subject}</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    border: 1px solid #eee;
                }}
                .header {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    border-bottom: 1px solid #dee2e6;
                }}
                .content {{ padding: 20px 0; }}
                .footer {{
                    padding: 20px 0;
                    text-align: center;
                    border-top: 1px solid #dee2e6;
                    color: #6c757d;
                    font-size: 12px;
                }}
                .highlight {{
                    background-color: #e7f3ff;
                    padding: 15px;
                    border-left: 4px solid #007bff;
                    margin: 15px 0;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>2c2a 验证码服务</h2>
                </div>
                <div class="content">
                    <p>您好！</p>
                    <div class="highlight">
                        <p><strong>这是一封测试邮件，用于验证邮件配置是否正确。</strong></p>
                    </div>
                    <p>系统配置的SMTP服务器可以正常发送邮件。</p>
                    <p>测试时间: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                </div>
                <div class="footer">
                    <p>&copy; 2026 2c2a. All rights reserved.</p>
                    <p>此邮件由系统自动发送，请勿回复。</p>
                </div>
            </div>
        </body>
        </html>
        '''

        email_service.send_email(
            to_emails=[test_email],
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

        task_record.complete_success(
            result_data={'test_email': test_email}
        )
    except Exception as exc:
        logger.error(f'测试邮件发送失败: {exc}', exc_info=True)
        task_record.complete_failure(str(exc))
