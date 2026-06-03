"""
用户管理模型
"""
import uuid as _uuid

from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


class User(AbstractUser):
    """
    自定义用户模型

    扩展Django默认用户模型，添加额外字段
    """
    # 基本信息
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_('手机号码'),
        help_text=_('用户的手机号码')
    )
    avatar = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name=_('头像'),
        help_text=_('用户头像图片')
    )

    # 状态信息
    is_verified = models.BooleanField(
        default=False,
        verbose_name=_('已验证'),
        help_text=_('用户邮箱是否已验证')
    )
    last_login_ip = models.GenericIPAddressField(
        blank=True,
        null=True,
        verbose_name=_('最后登录IP'),
        help_text=_('用户最后一次登录的IP地址')
    )

    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间'),
        help_text=_('用户账号创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间'),
        help_text=_('用户信息最后更新时间')
    )

    site_groups = models.ManyToManyField(
        'dashboard.SiteGroup',
        blank=True,
        related_name='members',
        verbose_name=_('所属站点组'),
        help_text=_('用户所属的站点组，决定用户可见的数据范围'),
    )

    class Meta:
        verbose_name = _('用户')
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        """返回用户名"""
        return self.username

    def get_full_name(self):
        """获取用户全名"""
        full_name = super().get_full_name()
        return full_name if full_name else self.username

    def is_site_group_admin(self, site_group=None):
        if self.is_superuser:
            return True
        if site_group is None:
            return False
        return site_group.admins.filter(pk=self.pk).exists()

    def get_adminable_site_groups(self):
        if self.is_superuser:
            from apps.dashboard.models import SiteGroup
            return SiteGroup.objects.all()
        return self.admin_site_groups.all()

    def sync_staff_status(self):
        if self.is_superuser:
            if not self.is_staff:
                self.is_staff = True
                self.save(update_fields=['is_staff'])
            return

        has_auto_staff = self.groups.filter(
            profile__auto_staff=True
        ).exists()

        if has_auto_staff != self.is_staff:
            self.is_staff = has_auto_staff
            self.save(update_fields=['is_staff'])

    def update_last_login(self, request):
        """
        更新最后登录信息

        Args:
            request: Django请求对象
        """
        from utils.helpers import get_client_ip
        self.last_login = timezone.now()
        self.last_login_ip = get_client_ip(request)
        self.save(update_fields=['last_login', 'last_login_ip'])


class UserProfile(models.Model):
    """
    用户资料模型

    存储用户的详细资料信息
    """
    # 关联用户
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_('用户'),
        help_text=_('关联的用户')
    )

    # 个人信息
    nickname = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_('昵称'),
        help_text=_('用户昵称')
    )
    gender = models.CharField(
        max_length=10,
        choices=[
            ('male', _('男')),
            ('female', _('女')),
            ('other', _('其他')),
        ],
        blank=True,
        verbose_name=_('性别'),
        help_text=_('用户性别')
    )
    birthday = models.DateField(
        blank=True,
        null=True,
        verbose_name=_('生日'),
        help_text=_('用户生日')
    )
    location = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_('所在地'),
        help_text=_('用户所在地')
    )
    bio = models.TextField(
        blank=True,
        verbose_name=_('个人简介'),
        help_text=_('用户个人简介')
    )

    # 通知设置
    email_notification = models.BooleanField(
        default=True,
        verbose_name=_('邮件通知'),
        help_text=_('是否接收邮件通知')
    )
    system_notification = models.BooleanField(
        default=True,
        verbose_name=_('系统通知'),
        help_text=_('是否接收系统通知')
    )

    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间'),
        help_text=_('资料创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间'),
        help_text=_('资料最后更新时间')
    )

    class Meta:
        verbose_name = _('用户资料')
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        """返回用户昵称或用户名"""
        return self.nickname or self.user.username


class LoginLog(models.Model):
    """
    登录日志模型

    记录用户的登录历史
    """
    # 关联用户
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='login_logs',
        verbose_name=_('用户'),
        help_text=_('登录的用户')
    )

    # 登录信息
    ip_address = models.GenericIPAddressField(
        verbose_name=_('IP地址'),
        help_text=_('登录时的IP地址')
    )
    user_agent = models.TextField(
        blank=True,
        verbose_name=_('用户代理'),
        help_text=_('登录时的浏览器信息')
    )
    login_type = models.CharField(
        max_length=20,
        choices=[
            ('web', _('网页登录')),
            ('api', _('API登录')),
            ('other', _('其他')),
        ],
        default='web',
        verbose_name=_('登录方式'),
        help_text=_('用户的登录方式')
    )
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', _('成功')),
            ('failed', _('失败')),
        ],
        verbose_name=_('登录状态'),
        help_text=_('登录是否成功')
    )
    failure_reason = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_('失败原因'),
        help_text=_('登录失败的原因')
    )

    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('登录时间'),
        help_text=_('登录发生的时间')
    )

    class Meta:
        verbose_name = _('登录日志')
        verbose_name_plural = verbose_name
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        """返回登录信息"""
        return (
            f'{self.user.username if self.user else "未知用户"}'
            f' - {self.ip_address}'
        )


class GroupProfile(models.Model):
    group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name=_('用户组'),
        help_text=_('关联的Django用户组')
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_('默认组'),
        help_text=_('默认组不可删除，系统预设角色')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('描述'),
        help_text=_('用户组的功能描述')
    )
    auto_staff = models.BooleanField(
        default=False,
        verbose_name=_('自动员工'),
        help_text=_('勾选后，属于该组的用户将自动获得员工身份(is_staff)')
    )
    sort_order = models.IntegerField(
        default=0,
        verbose_name=_('排序'),
        help_text=_('数值越小排序越靠前')
    )

    class Meta:
        verbose_name = _('用户组配置')
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'group__name']

    def __str__(self):
        default_tag = ' [默认]' if self.is_default else ''
        return f'{self.group.name}{default_tag}'


class RegistrationLink(models.Model):
    token = models.CharField(
        max_length=64,
        unique=True,
        default=_uuid.uuid4,
        verbose_name=_('令牌'),
        help_text=_('注册链接的唯一标识')
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name='registration_links',
        verbose_name=_('注册后用户组'),
        help_text=_('通过此链接注册的用户将自动加入该用户组')
    )
    created_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_registration_links',
        verbose_name=_('创建者'),
        help_text=_('创建此注册链接的管理员')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )
    max_uses = models.IntegerField(
        default=1,
        verbose_name=_('最大使用次数'),
        help_text=_('设置为0表示不限制使用次数')
    )
    used_count = models.IntegerField(
        default=0,
        verbose_name=_('已使用次数')
    )
    used = models.BooleanField(
        default=False,
        verbose_name=_('已使用'),
        help_text=_('此注册链接是否已被使用')
    )
    used_by = models.ForeignKey(
        'User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='used_registration_link',
        verbose_name=_('最后使用者'),
        help_text=_('最后使用此链接注册的用户')
    )
    used_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('最后使用时间')
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('过期时间'),
        help_text=_('留空表示永不过期')
    )
    note = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_('备注'),
        help_text=_('管理员备注，仅后台可见')
    )

    class Meta:
        verbose_name = _('注册链接')
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        if self.max_uses == 0:
            usage = f'已用{self.used_count}次/不限'
        else:
            usage = f'已用{self.used_count}/{self.max_uses}次'
        return f'注册链接({self.group.name}) - {usage}'

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_exhausted(self):
        if self.max_uses == 0:
            return False
        return self.used_count >= self.max_uses

    @property
    def is_valid(self):
        return not self.is_exhausted and not self.is_expired

    def increment_usage(self, user):
        from django.db.models import F
        RegistrationLink.objects.filter(pk=self.pk).update(
            used_count=F('used_count') + 1,
            used_by=user,
            used_at=timezone.now(),
        )
        self.refresh_from_db()
        if self.max_uses > 0 and self.used_count >= self.max_uses:
            RegistrationLink.objects.filter(pk=self.pk).update(used=True)
            self.used = True
        else:
            RegistrationLink.objects.filter(pk=self.pk).update(used=False)
            self.used = False
