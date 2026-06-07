import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, smtp_host: str, smtp_port: int,
                 smtp_username: str, smtp_password: str,
                 smtp_from_email: str, smtp_encryption: str = 'TLS',
                 smtp_from_name: Optional[str] = None):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_from_email = smtp_from_email
        self.smtp_encryption = smtp_encryption
        self.smtp_from_name = smtp_from_name

    def send_email(
        self,
        to_emails: List[str],
        subject: str,
        text_body: str,
        html_body: Optional[str] = None,
        from_email: Optional[str] = None,
    ) -> bool:
        if not all([self.smtp_host, self.smtp_port,
                    self.smtp_username, self.smtp_password,
                    self.smtp_from_email]):
            raise ValidationError('SMTP配置不完整')

        sender = from_email or self.smtp_from_email

        msg = MIMEMultipart('alternative')
        msg['From'] = sender
        msg['To'] = ', '.join(to_emails)
        msg['Subject'] = subject

        part1 = MIMEText(text_body, 'plain', 'utf-8')
        msg.attach(part1)

        if html_body:
            part2 = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(part2)

        server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        try:
            server.ehlo()

            if self.smtp_use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)
                server.ehlo()

            server.login(self.smtp_username, self.smtp_password)
            text = msg.as_string()
            server.sendmail(sender, to_emails, text)
        finally:
            try:
                server.quit()
            except smtplib.SMTPServerDisconnected:
                pass

        return True

    @classmethod
    def from_system_config(cls, config):
        return cls(
            smtp_host=config.smtp_host,
            smtp_port=config.smtp_port,
            smtp_username=config.smtp_username,
            smtp_password=config.smtp_password,
            smtp_from_email=config.smtp_from_email,
            smtp_encryption=config.smtp_encryption,
            smtp_from_name=config.smtp_from_name,
        )

    @staticmethod
    def send_email_async(
        to_emails,
        subject,
        text_body,
        html_body=None,
        from_email=None,
    ):
        """异步发送邮件，通过 Celery 任务执行"""
        from .tasks import send_email_task
        send_email_task.delay(
            to_emails=to_emails,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            from_email=from_email,
        )
