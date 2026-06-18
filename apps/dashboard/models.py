"""
仪表盘数据模型
"""
from django.db import models
from django.conf import settings
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
    SMTP_ENCRYPTION_TYPES = (
        ('NONE', '无加密'),
        ('TLS', 'TLS (STARTTLS)'),
        ('SSL', 'SSL (SMTPS)'),
    )

    smtp_encryption = models.CharField(
        max_length=8,
        choices=SMTP_ENCRYPTION_TYPES,
        default='TLS',
        verbose_name='加密方式',
        help_text='TLS: 端口通常为587；SSL: 端口通常为465'
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
    smtp_from_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='发件人名称',
        help_text='系统发送邮件时显示的发件人名称，如"XX云服务"'
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
    site_icon = models.CharField(
        max_length=500,
        blank=True,
        default='',
        verbose_name='站点图标',
        help_text='站点图标路径，如 /media/branding/icon.svg，留空使用默认图标'
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

    hostname_branding = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='主机名品牌绑定',
        help_text=(
            '按主机名绑定专用站点名和图标，格式：\n'
            '{"host.example.com": {"site_name": "站点名", "site_icon": "/media/branding/icon.svg"}}\n'
            '未配置的主机名使用全局默认值'
        )
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

    def get_branding_for_hostname(self, hostname):
        if self.hostname_branding and hostname in self.hostname_branding:
            return self.hostname_branding[hostname]
        return {}

    def get_site_name_for_hostname(self, hostname):
        branding = self.get_branding_for_hostname(hostname)
        return branding.get('site_name') or self.site_name

    def get_site_icon_for_hostname(self, hostname):
        branding = self.get_branding_for_hostname(hostname)
        return branding.get('site_icon') or '/static/img/favicon.svg'


class SiteGroup(models.Model):
    name = models.CharField('站点组名称', max_length=100, help_text='站点组的显示名称')
    slug = models.SlugField('标识符', max_length=100, unique=True, help_text='唯一标识符，用于URL和内部引用')
    description = models.TextField('描述', blank=True, help_text='站点组的描述信息')
    site_name = models.CharField('站点名称', max_length=100, blank=True, help_text='该站点组的站点名称，留空则使用全局默认值')
    site_icon = models.CharField('站点图标', max_length=500, blank=True, help_text='该站点组的站点图标路径，留空则使用全局默认值')
    is_active = models.BooleanField('是否启用', default=True, help_text='禁用后该站点组的所有功能将不可用')
    admins = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name='admin_site_groups',
        verbose_name='站点组管理员',
        help_text='该站点组的管理员，在当前站点组内拥有类似超级管理员的权限',
    )
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '站点组'
        verbose_name_plural = '站点组'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        result = super().save(*args, **kwargs)
        for hostname in self.hostnames.values_list('hostname', flat=True):
            cache.delete(f'site_group:hostname:{hostname}')
        return result

    def delete(self, *args, **kwargs):
        from django.core.cache import cache
        hostnames = list(self.hostnames.values_list('hostname', flat=True))
        result = super().delete(*args, **kwargs)
        for hostname in hostnames:
            cache.delete(f'site_group:hostname:{hostname}')
        return result


class SiteGroupConfig(models.Model):
    """
    站点组配置覆盖模型

    允许每个站点组覆盖 SystemConfig 中的配置项。
    字段留空(null)表示使用 SystemConfig 的全局默认值。
    """
    site_group = models.OneToOneField(
        SiteGroup,
        on_delete=models.CASCADE,
        related_name='config',
        verbose_name='站点组',
        help_text='关联的站点组',
    )

    # SMTP 配置覆盖
    smtp_host = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name='SMTP服务器',
        help_text='留空使用全局配置',
    )
    smtp_port = models.IntegerField(
        blank=True, null=True,
        verbose_name='SMTP端口',
        help_text='留空使用全局配置',
    )
    smtp_encryption = models.CharField(
        max_length=8,
        choices=SystemConfig.SMTP_ENCRYPTION_TYPES,
        blank=True, null=True,
        verbose_name='加密方式',
        help_text='留空使用全局配置',
    )
    smtp_username = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name='SMTP用户名',
        help_text='留空使用全局配置',
    )
    smtp_password = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name='SMTP密码',
        help_text='留空使用全局配置',
    )
    smtp_from_email = models.EmailField(
        blank=True, null=True,
        verbose_name='发件人邮箱',
        help_text='留空使用全局配置',
    )
    smtp_from_name = models.CharField(
        max_length=255, blank=True, null=True,
        verbose_name='发件人名称',
        help_text='留空使用全局配置',
    )

    # 验证码配置覆盖
    captcha_provider = models.CharField(
        max_length=32,
        choices=(('none', '无'), ('tianai', '天爱验证码')),
        blank=True, null=True,
        verbose_name='验证码提供器',
        help_text='留空使用全局配置',
    )
    captcha_type = models.CharField(
        max_length=32,
        choices=SystemConfig.CAPTCHA_TYPES,
        blank=True, null=True,
        verbose_name='默认验证码类型',
        help_text='留空使用全局配置',
    )
    login_captcha_type = models.CharField(
        max_length=32,
        choices=SystemConfig.CAPTCHA_TYPES,
        blank=True, null=True,
        verbose_name='登录验证码类型',
        help_text='留空使用全局配置',
    )
    register_captcha_type = models.CharField(
        max_length=32,
        choices=SystemConfig.CAPTCHA_TYPES,
        blank=True, null=True,
        verbose_name='注册验证码类型',
        help_text='留空使用全局配置',
    )
    email_captcha_type = models.CharField(
        max_length=32,
        choices=SystemConfig.CAPTCHA_TYPES,
        blank=True, null=True,
        verbose_name='邮箱验证码类型',
        help_text='留空使用全局配置',
    )

    # 注册与邮箱配置覆盖
    enable_registration = models.BooleanField(
        blank=True, null=True,
        verbose_name='启用用户注册',
        help_text='留空使用全局配置',
    )
    email_suffix_whitelist = models.TextField(
        blank=True, null=True,
        verbose_name='邮箱后缀白名单',
        help_text='留空使用全局配置。每行一个后缀',
    )
    email_suffix_blacklist = models.TextField(
        blank=True, null=True,
        verbose_name='邮箱后缀黑名单',
        help_text='留空使用全局配置。每行一个后缀',
    )

    # 站点外观配置覆盖
    site_name = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name='站点名称',
        help_text='留空使用全局配置',
    )
    site_icon = models.CharField(
        max_length=500, blank=True, null=True,
        verbose_name='站点图标',
        help_text='留空使用全局配置。图标路径，如 /media/branding/icon.svg',
    )
    icp_number = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name='ICP备案号',
        help_text='留空使用全局配置',
    )
    police_number = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name='公安备案号',
        help_text='留空使用全局配置',
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '站点组配置'
        verbose_name_plural = '站点组配置'

    def __str__(self):
        return f'{self.site_group.name} 配置'

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        result = super().save(*args, **kwargs)
        cache.delete(f'site_group_config:{self.site_group_id}')
        return result

    def delete(self, *args, **kwargs):
        from django.core.cache import cache
        cache.delete(f'site_group_config:{self.site_group_id}')
        return super().delete(*args, **kwargs)

    @classmethod
    def get_config(cls, site_group):
        """获取站点组配置（带缓存）"""
        if site_group is None:
            return None
        from django.core.cache import cache
        cache_key = f'site_group_config:{site_group.pk}'
        config = cache.get(cache_key)
        if config is not None:
            return config
        config, _ = cls.objects.get_or_create(site_group=site_group)
        cache.set(cache_key, config, timeout=300)
        return config


class SiteGroupHostname(models.Model):
    hostname = models.CharField('主机名', max_length=255, unique=True, help_text='HTTP Host头中的主机名（不含端口），如 demo.example.com')
    site_group = models.ForeignKey(
        SiteGroup,
        on_delete=models.CASCADE,
        related_name='hostnames',
        verbose_name='所属站点组',
        help_text='该主机名所属的站点组',
    )

    class Meta:
        verbose_name = '站点组主机名'
        verbose_name_plural = '站点组主机名'

    def __str__(self):
        return f'{self.hostname} -> {self.site_group.name}'

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        result = super().save(*args, **kwargs)
        cache.delete(f'site_group:hostname:{self.hostname}')
        return result

    def delete(self, *args, **kwargs):
        from django.core.cache import cache
        hostname = self.hostname
        result = super().delete(*args, **kwargs)
        cache.delete(f'site_group:hostname:{hostname}')
        return result
