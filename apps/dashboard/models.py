"""
仪表盘数据模型
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class DashboardWidget(models.Model):
    """
    仪表盘组件模型
    用于配置仪表盘上的各种组件
    """
    class Meta:
        verbose_name = '仪表盘组件'
        verbose_name_plural = verbose_name
        ordering = ['display_order']
        indexes = [
            models.Index(fields=['widget_type']),
            models.Index(fields=['is_enabled']),
            models.Index(fields=['display_order']),
        ]

    WIDGET_TYPES = (
        ('stat_card', '统计卡片'),
        ('chart', '图表'),
        ('recent_operations', '最近操作'),
        ('host_status', '主机状态'),
        ('system_alerts', '系统告警'),
    )

    widget_type = models.CharField(
        '组件类型',
        max_length=50,
        choices=WIDGET_TYPES,
        help_text='组件的类型'
    )
    title = models.CharField(
        '标题',
        max_length=200,
        help_text='组件显示的标题'
    )
    display_order = models.IntegerField(
        '显示顺序',
        default=0,
        help_text='组件在仪表盘上的显示顺序'
    )
    is_enabled = models.BooleanField(
        '是否启用',
        default=True,
        help_text='组件是否在仪表盘上显示'
    )
    widget_config = models.JSONField(
        '组件配置',
        default=dict,
        blank=True,
        help_text='组件的配置参数'
    )
    created_at = models.DateTimeField(
        '创建时间',
        auto_now_add=True,
        help_text='组件创建时间'
    )
    updated_at = models.DateTimeField(
        '更新时间',
        auto_now=True,
        help_text='组件更新时间'
    )

    def __str__(self):
        return self.title


class SystemConfig(models.Model):
    """
    系统配置模型

    用于存储系统的全局配置，如SMTP服务器、验证码服务等
    """
    # SMTP配置
    smtp_host = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='SMTP服务器',
        help_text='SMTP服务器地址，如smtp.gmail.com'
    )
    smtp_port = models.IntegerField(
        blank=True,
        null=True,
        verbose_name='SMTP端口',
        help_text='SMTP服务器端口，通常为587或465'
    )
    smtp_use_tls = models.BooleanField(
        default=True,
        verbose_name='使用TLS',
        help_text='是否使用TLS加密连接'
    )
    smtp_username = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='SMTP用户名',
        help_text='SMTP登录用户名，通常是邮箱地址'
    )
    smtp_password = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='SMTP密码',
        help_text='SMTP登录密码或应用专用密码'
    )
    smtp_from_email = models.EmailField(
        blank=True,
        null=True,
        verbose_name='发件人邮箱',
        help_text='系统发送邮件时使用的发件人地址'
    )

    CAPTCHA_TYPES = (
        ('SLIDER', '滑块验证'),
        ('ROTATE', '旋转验证'),
        ('CONCAT', '滑动还原'),
        ('WORD_IMAGE_CLICK', '文字点选'),
    )

    captcha_provider = models.CharField(
        max_length=32,
        choices=(
            ('none', '无'),
            ('tianai', '天爱验证码'),
        ),
        default='none',
        verbose_name='验证码提供器',
        help_text='选择要启用的验证码提供器'
    )
    captcha_type = models.CharField(
        max_length=32,
        choices=CAPTCHA_TYPES,
        default='SLIDER',
        verbose_name='默认验证码类型',
        help_text='全局默认的验证码类型'
    )
    login_captcha_type = models.CharField(
        max_length=32,
        choices=CAPTCHA_TYPES,
        blank=True,
        null=True,
        verbose_name='登录验证码类型',
        help_text='登录场景的验证码类型（留空则使用默认类型）'
    )
    register_captcha_type = models.CharField(
        max_length=32,
        choices=CAPTCHA_TYPES,
        blank=True,
        null=True,
        verbose_name='注册验证码类型',
        help_text='注册场景的验证码类型（留空则使用默认类型）'
    )
    email_captcha_type = models.CharField(
        max_length=32,
        choices=CAPTCHA_TYPES,
        blank=True,
        null=True,
        verbose_name='邮箱验证码类型',
        help_text='邮箱发送验证码场景的验证码类型（留空则使用默认类型）'
    )

    # 其他配置
    site_name = models.CharField(
        max_length=100,
        default='2c2a',
        verbose_name='站点名称',
        help_text='系统显示的站点名称'
    )

    # 注册开关
    enable_registration = models.BooleanField(
        default=False,
        verbose_name='启用用户注册',
        help_text='是否开启用户注册功能，默认为关闭'
    )

    # ICP备案号配置
    icp_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ICP备案号',
        help_text='ICP备案号，例如：京ICP备12345678号'
    )

    # 公安备案号配置
    police_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='公安备案号',
        help_text='公安备案号，例如：京公网安备 11010502000000号'
    )

    email_suffix_whitelist = models.TextField(
        blank=True,
        null=True,
        verbose_name='邮箱后缀白名单',
        help_text=(
            '允许注册的邮箱后缀列表，每行一个后缀，'
            '例如：\n@example.com\n@gmail.com\n@company.com\n'
            '留空表示不限制'
        )
    )
    email_suffix_blacklist = models.TextField(
        blank=True,
        null=True,
        verbose_name='邮箱后缀黑名单',
        help_text=(
            '禁止注册的邮箱后缀列表，每行一个后缀，'
            '例如：\n@tempmail.com\n@spam.com\n'
            '留空表示不限制'
        )
    )

    local_access_locked = models.BooleanField(
        default=False,
        verbose_name='禁止本地访问',
        help_text='启用后将禁止来自 localhost/127.0.0.1 的访问'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='创建时间'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='更新时间'
    )

    class Meta:
        verbose_name = '系统配置'
        verbose_name_plural = '系统配置'

    def __str__(self):
        return f'{self.site_name} 配置'

    def clean(self):
        pass

    @classmethod
    def get_config(cls):
        """获取当前系统配置（带缓存）"""
        from django.core.cache import cache
        cache_key = 'system_config:singleton'
        config = cache.get(cache_key)
        if config is not None:
            return config
        config, created = cls.objects.get_or_create(pk=1)
        cache.set(cache_key, config, timeout=300)
        return config

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        result = super().save(*args, **kwargs)
        cache.delete('system_config:singleton')
        return result

    def delete(self, *args, **kwargs):
        from django.core.cache import cache
        result = super().delete(*args, **kwargs)
        cache.delete('system_config:singleton')
        return result

    def get_captcha_config(self, scene=None):
        provider = self.captcha_provider
        if scene == 'login':
            captcha_type = self.login_captcha_type or self.captcha_type
        elif scene == 'register':
            captcha_type = self.register_captcha_type or self.captcha_type
        elif scene == 'email':
            captcha_type = self.email_captcha_type or self.captcha_type
        else:
            captcha_type = self.captcha_type
        return provider, captcha_type
