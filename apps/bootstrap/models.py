from django.db import models
from apps.hosts.models import Host
import uuid
from django.utils import timezone
from datetime import timedelta
import secrets as _secrets
from django.conf import settings


class InitialToken(models.Model):
    """初始配置令牌表 - 基于配对码的简化认证机制"""
    STATUS_CHOICES = [
        ('ISSUED', '已签发'),
        ('PAIRED', '已配对'),
        ('CONSUMED', '已消耗'),
    ]

    MAX_PAIRING_ATTEMPTS = 5

    token = models.CharField(max_length=255, primary_key=True, verbose_name="AccessToken")
    host = models.ForeignKey(Host, on_delete=models.CASCADE, verbose_name="关联的主机", null=True, blank=True)
    expires_at = models.DateTimeField(verbose_name="AccessToken过期时间")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ISSUED', verbose_name="状态")
    pairing_code = models.CharField(max_length=6, verbose_name="配对码", blank=True, null=True)
    pairing_code_expires_at = models.DateTimeField(verbose_name="配对码过期时间", blank=True, null=True)
    pairing_attempts = models.IntegerField(default=0, verbose_name="配对码验证尝试次数")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")

    class Meta:
        verbose_name = "初始令牌"
        verbose_name_plural = "初始令牌"
        db_table = "initial_token"

    def generate_pairing_code(self):
        """生成6位数字配对码"""
        code = f"{_secrets.randbelow(1000000):06d}"
        self.pairing_code = code
        self.pairing_code_expires_at = timezone.now() + timedelta(minutes=5)
        self.pairing_attempts = 0
        self.save(update_fields=['pairing_code', 'pairing_code_expires_at', 'pairing_attempts'])
        return code

    def verify_pairing_code(self, input_code):
        """验证配对码是否正确且未过期，含尝试次数限制"""
        if not self.pairing_code or not self.pairing_code_expires_at:
            return False

        if timezone.now() > self.pairing_code_expires_at:
            return False

        from django.db.models import F
        InitialToken.objects.filter(pk=self.pk).update(
            pairing_attempts=F('pairing_attempts') + 1
        )
        self.refresh_from_db()

        if self.pairing_attempts >= self.MAX_PAIRING_ATTEMPTS:
            self.pairing_code = None
            self.pairing_code_expires_at = None
            self.save(update_fields=['pairing_code', 'pairing_code_expires_at'])
            return False

        if self.pairing_code != input_code:
            return False

        self.status = 'PAIRED'
        self.pairing_code = None
        self.pairing_code_expires_at = None
        self.pairing_attempts = 0
        self.save(update_fields=['status', 'pairing_code', 'pairing_code_expires_at', 'pairing_attempts'])
        return True


class ActiveSession(models.Model):
    """活动会话表 - 基于配对码认证的会话管理"""
    session_token = models.CharField(max_length=255, primary_key=True, verbose_name="临时凭证")
    host = models.ForeignKey(Host, on_delete=models.CASCADE, verbose_name="关联的主机")
    bound_ip = models.GenericIPAddressField(verbose_name="绑定的请求源IP")
    expires_at = models.DateTimeField(verbose_name="会话过期时间")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    
    class Meta:
        verbose_name = "活动会话"
        verbose_name_plural = "活动会话"
        db_table = "active_session"