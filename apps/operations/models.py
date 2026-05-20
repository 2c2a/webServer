"""
操作记录模型
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from django.dispatch import Signal
import logging
import hashlib
import base64

User = get_user_model()

logger = logging.getLogger(__name__)


def _get_fernet():
    from cryptography.fernet import Fernet
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))

# 定义开户申请提交前的信号
account_opening_request_pre_submit = Signal()
# 定义开户申请提交后的信号
account_opening_request_post_submit = Signal()


class PublicHostInfo(models.Model):
    """
    公开主机信息模型

    用于在前端展示主机信息，而不暴露敏感信息
    """
    # 内部主机关联
    internal_host = models.OneToOneField(
        'hosts.Host',
        on_delete=models.CASCADE,
        verbose_name=_('内部主机'),
        help_text=_('关联的内部主机')
    )
    
    # 显示信息
    display_name = models.CharField(
        max_length=200,
        verbose_name=_('显示名称'),
        help_text=_('在前端展示的主机名称')
    )
    display_description = models.TextField(
        blank=True,
        verbose_name=_('显示描述'),
        help_text=_('在前端展示的主机描述，支持Markdown格式')
    )
    
    # 连接信息（对外公开的部分）
    display_hostname = models.CharField(
        max_length=255,
        verbose_name=_('显示地址'),
        help_text=_('在前端展示的主机地址')
    )
    display_rdp_port = models.IntegerField(
        default=3389,
        verbose_name=_('显示RDP端口'),
        help_text=_('在前端展示的RDP端口')
    )
    
    # 可用性
    is_available = models.BooleanField(
        default=True,
        verbose_name=_('是否可用'),
        help_text=_('是否在前端展示此主机')
    )
    
    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间')
    )

    class Meta:
        verbose_name = _('公开主机信息')
        verbose_name_plural = _('公开主机信息')
        indexes = [
            models.Index(fields=['is_available']),
            models.Index(fields=['internal_host']),
        ]

    def __str__(self):
        return self.display_name


class SystemTask(models.Model):
    """
    系统任务模型

    记录系统中的异步任务，如批量操作、定时任务等
    """
    # 任务信息
    name = models.CharField(
        max_length=200,
        verbose_name=_('任务名称'),
        help_text=_('任务的名称')
    )
    task_type = models.CharField(
        max_length=100,
        verbose_name=_('任务类型'),
        help_text=_('任务的类型，如batch_create_user等')
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('任务描述'),
        help_text=_('任务的详细描述')
    )

    # 执行信息
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', _('等待中')),
            ('running', _('执行中')),
            ('success', _('成功')),
            ('failed', _('失败')),
            ('cancelled', _('已取消')),
        ],
        default='pending',
        verbose_name=_('任务状态'),
        help_text=_('任务的执行状态')
    )
    progress = models.IntegerField(
        default=0,
        verbose_name=_('执行进度'),
        help_text=_('任务执行进度，0-100')
    )
    result = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('执行结果'),
        help_text=_('任务执行的结果信息')
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('错误信息'),
        help_text=_('任务执行失败时的错误信息')
    )

    # 关联信息
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_tasks',
        verbose_name=_('创建者'),
        help_text=_('创建该任务的用户')
    )

    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间'),
        help_text=_('任务创建时间')
    )
    started_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_('开始时间'),
        help_text=_('任务开始执行的时间')
    )
    completed_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name=_('完成时间'),
        help_text=_('任务完成的时间')
    )

    class Meta:
        verbose_name = _('系统任务')
        verbose_name_plural = _('系统任务')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['task_type']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        """返回任务名称"""
        return self.name

    def update_progress(self, progress):
        """
        更新任务进度

        Args:
            progress: 进度值，0-100
        """
        self.progress = min(max(progress, 0), 100)
        self.save(update_fields=['progress'])

    def start(self):
        """开始执行任务"""
        from django.utils import timezone
        self.status = 'running'
        self.started_at = timezone.now()
        self.save(update_fields=['status', 'started_at'])

    def complete(self, result=None):
        """
        完成任务

        Args:
            result: 执行结果
        """
        from django.utils import timezone
        self.status = 'success'
        self.completed_at = timezone.now()
        self.progress = 100
        if result:
            self.result = result
        self.save(update_fields=['status', 'completed_at', 'progress', 'result'])

    def fail(self, error_message):
        """
        任务失败

        Args:
            error_message: 错误信息
        """
        from django.utils import timezone
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'completed_at', 'error_message'])

    def cancel(self):
        """取消任务"""
        from django.utils import timezone
        self.status = 'cancelled'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])


class ProductGroup(models.Model):
    """
    产品组模型
    
    用于对产品进行分组管理
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('产品组名称'),
        help_text=_('产品组的名称')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('产品组描述'),
        help_text=_('产品组的详细描述，支持Markdown格式')
    )
    display_order = models.IntegerField(
        default=0,
        verbose_name=_('显示顺序'),
        help_text=_('产品组在前端展示的顺序，数字越小越靠前')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('是否启用'),
        help_text=_('是否在前端展示此产品组')
    )
    visibility = models.CharField(
        max_length=20,
        choices=[
            ('public', _('公开')),
            ('invite_only', _('邀请访问')),
        ],
        default='public',
        verbose_name=_('可见性'),
        help_text=_('产品组的可见性：公开对所有用户可见，邀请访问仅对已授权用户可见')
    )
    auto_assign_providers = models.ManyToManyField(
        User,
        blank=True,
        related_name='auto_product_groups',
        verbose_name=_('自动分配提供商'),
        help_text=_('这些提供商创建的产品将自动加入此产品组')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_product_groups',
        verbose_name=_('创建者'),
        help_text=_('创建此产品组的用户')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间')
    )

    class Meta:
        verbose_name = _('产品组')
        verbose_name_plural = _('产品组')
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['display_order']),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    产品模型

    代表面向用户的产品，一个主机可以对应多个产品
    """
    name = models.CharField(
        max_length=200,
        verbose_name=_('产品名称'),
        help_text=_('面向用户展示的产品名称')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('产品描述'),
        help_text=_('产品的详细描述，支持Markdown格式')
    )
    display_name = models.CharField(
        max_length=200,
        verbose_name=_('显示名称'),
        help_text=_('在前端展示的产品名称')
    )
    display_description = models.TextField(
        blank=True,
        verbose_name=_('显示描述'),
        help_text=_('在前端展示的产品描述，支持Markdown格式')
    )
    
    product_group = models.ForeignKey(
        ProductGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name=_('产品组'),
        help_text=_('产品所属的产品组')
    )
    
    # 关联主机
    host = models.ForeignKey(
        'hosts.Host',
        on_delete=models.CASCADE,
        verbose_name=_('关联主机'),
        help_text=_('此产品运行所在的主机')
    )
    
    # 产品配置
    rdp_port = models.IntegerField(
        default=3389,
        verbose_name=_('RDP端口'),
        help_text=_('用户连接时使用的RDP端口')
    )
    display_hostname = models.CharField(
        max_length=255,
        verbose_name=_('显示地址'),
        help_text=_('在前端展示的产品访问地址')
    )
    
    # 产品状态
    is_available = models.BooleanField(
        default=True,
        verbose_name=_('是否可用'),
        help_text=_('是否在前端展示此产品')
    )
    auto_approval = models.BooleanField(
        default=False,
        verbose_name=_('自动审核'),
        help_text=_('是否自动批准针对此产品的开户申请')
    )
    visibility = models.CharField(
        max_length=20,
        choices=[
            ('public', _('公开')),
            ('invite_only', _('邀请访问')),
        ],
        default='public',
        verbose_name=_('可见性'),
        help_text=_('产品的可见性：公开对所有用户可见，邀请访问仅对已授权用户可见')
    )

    enable_disk_quota = models.BooleanField(
        default=False,
        verbose_name=_('启用磁盘配额管理'),
        help_text=_('是否启用磁盘配额管理，启用后将自动为新用户设置磁盘配额')
    )
    enable_host_protection = models.BooleanField(
        default=False,
        verbose_name=_('启用主机保护(通过Gateway)'),
        help_text=_(
            '启用后，用户只能通过Gateway隧道访问该产品的RDP，'
            '主机不暴露公网IP。需要部署Gateway服务。'
        )
    )
    default_disk_quota = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('默认磁盘配额'),
        help_text=_('每个磁盘的默认配额大小（MB），如 {"C:": 10240, "D:": 20480}')
    )
    allow_extra_quota_disks = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_('允许额外申请容量的磁盘'),
        help_text=_('允许用户在申请时额外申请容量的磁盘列表，如 ["C:", "D:"]')
    )
    
    # 创建者
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('创建者'),
        help_text=_('创建此产品的用户'),
        related_name='created_products'
    )
    
    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间')
    )

    class Meta:
        verbose_name = _('产品')
        verbose_name_plural = _('产品')
        indexes = [
            models.Index(fields=['is_available']),
            models.Index(fields=['host']),
            models.Index(fields=['created_at']),
            models.Index(fields=['created_by']),
            models.Index(fields=['product_group'], name='operations__product_981a27_idx'),
        ]

    def __str__(self):
        return self.display_name

    @property
    def status(self):
        """
        产品状态，继承自主机状态
        """
        return self.host.status

    @property
    def hostname(self):
        """
        产品主机名，使用显示地址
        """
        return self.display_hostname


class AccountOpeningRequest(models.Model):
    """
    用户开户申请模型

    用于记录用户提交的开户申请信息
    """
    # 申请人信息
    applicant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='account_opening_requests',
        verbose_name=_('申请人'),
        help_text=_('提交开户申请的用户')
    )
    contact_email = models.EmailField(
        verbose_name=_('联系邮箱'),
        help_text=_('申请人联系方式')
    )
    contact_phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name=_('联系电话'),
        help_text=_('申请人联系电话')
    )

    # 开户信息
    username = models.CharField(
        max_length=150,
        verbose_name=_('用户名'),
        help_text=_('希望在云电脑上创建的用户名')
    )
    user_fullname = models.CharField(
        max_length=200,
        verbose_name=_('用户姓名'),
        help_text=_('用户真实姓名')
    )
    user_email = models.EmailField(
        verbose_name=_('用户邮箱'),
        help_text=_('用户邮箱地址')
    )
    user_description = models.TextField(
        blank=True,
        verbose_name=_('用户描述'),
        help_text=_('关于该用户的附加信息')
    )

    # 目标产品（替代原来的target_host）
    target_product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name=_('目标产品'),
        help_text=_('要在哪个产品上创建用户'),
        null=True,
        blank=True
    )

    requested_disk_capacity = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('需求磁盘容量'),
        help_text=_('用户额外申请的磁盘容量（MB），如 {"C:": 20480, "D:": 40960}')
    )

    # 审核信息
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', _('待审核')),
            ('approved', _('已批准')),
            ('rejected', _('已拒绝')),
            ('processing', _('处理中')),
            ('completed', _('已完成')),
            ('failed', _('失败')),
        ],
        default='pending',
        verbose_name=_('申请状态'),
        help_text=_('开户申请的当前状态')
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_account_requests',
        verbose_name=_('审核人'),
        help_text=_('批准此申请的管理员')
    )
    approval_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('审核时间'),
        help_text=_('申请被审核的时间')
    )
    approval_notes = models.TextField(
        blank=True,
        verbose_name=_('审核备注'),
        help_text=_('审核时的备注信息')
    )

    # 结果信息
    cloud_user_id = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('云电脑用户ID'),
        help_text=_('在云电脑上实际创建的用户ID')
    )
    cloud_user_password = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('云电脑用户密码'),
        help_text=_('为用户设置的初始密码')
    )
    result_message = models.TextField(
        blank=True,
        verbose_name=_('结果信息'),
        help_text=_('开户操作的结果信息')
    )

    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间'),
        help_text=_('申请创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间'),
        help_text=_('申请信息最后更新时间')
    )

    class Meta:
        verbose_name = _('开户申请')
        verbose_name_plural = _('开户申请')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['applicant']),
            models.Index(fields=['status']),
            models.Index(fields=['target_product']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        product_name = self.target_product.display_name if self.target_product else 'Unknown Product'
        return f'{self.username} - {product_name}'

    def approve(self, approver, notes=''):
        """
        批准开户申请

        Args:
            approver: 批准申请的管理员
            notes: 审核备注
        """
        # 获取当前状态以判断是否从pending变更为approved
        old_status = self.status
        
        self.status = 'approved'
        self.approved_by = approver
        self.approval_date = timezone.now()
        self.approval_notes = notes
        # 不直接调用save，而是通过super().save()让重写的save方法处理后续操作
        super().save()
        
        # 如果之前的状态是pending，现在变更为approved，则触发自动创建
        if old_status == 'pending' and self.status == 'approved':
            self.auto_process_creation()

    def reject(self, approver, notes=''):
        """
        拒绝开户申请

        Args:
            approver: 拒绝申请的管理员
            notes: 审核备注
        """
        self.status = 'rejected'
        self.approved_by = approver
        self.approval_date = timezone.now()
        self.approval_notes = notes
        self.save()

    def start_processing(self):
        """
        开始处理开户申请
        """
        self.status = 'processing'
        self.save()

    def complete(self, cloud_user_id, cloud_user_password, result_message=''):
        """
        完成开户申请

        Args:
            cloud_user_id: 在云电脑上创建的用户ID
            cloud_user_password: 用户初始密码（出于安全考虑，不会存储）
            result_message: 结果信息
        """
        self.status = 'completed'
        self.cloud_user_id = cloud_user_id
        # 出于安全考虑，不存储用户密码明文
        # self.cloud_user_password = cloud_user_password
        self.result_message = result_message
        self.save()

    def fail(self, result_message=''):
        """
        开户申请失败

        Args:
            result_message: 失败原因
        """
        self.status = 'failed'
        self.result_message = result_message
        self.save()

    def save(self, *args, **kwargs):
        """
        重写save方法，当状态变为'approved'时自动处理用户创建
        """
        is_new_instance = not self.pk

        if is_new_instance:
            logger.info(f"AccountOpeningRequest.save(): 发送 pre-submit 信号，实例ID: {self.pk}, 目标产品: {getattr(self.target_product, 'id', 'None')}, 联系邮箱: {self.contact_email}")
            account_opening_request_pre_submit.send(sender=self.__class__, instance=self)
            logger.info(f"AccountOpeningRequest.save(): pre-submit 信号发送完成，实例状态: {self.status}")

        old_status = None
        if self.pk:
            try:
                old_status = AccountOpeningRequest.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            except Exception:
                pass

        auto_approved = False
        if (is_new_instance and self.target_product and 
            self.target_product.auto_approval and self.status == 'pending'):
            self.status = 'approved'
            from django.contrib.auth import get_user_model
            from typing import cast
            User = get_user_model()
            system_user = User.objects.filter(is_superuser=True).first()
            if system_user:
                self.approved_by = cast(User, system_user)
            self.approval_date = timezone.now()
            self.approval_notes = '自动审核通过'
            auto_approved = True

        super().save(*args, **kwargs)

        if is_new_instance:
            logger.info(f"AccountOpeningRequest.save(): 发送 post-submit 信号，实例ID: {self.pk}, 最终状态: {self.status}")
            account_opening_request_post_submit.send(sender=self.__class__, instance=self)

        if ((old_status == 'pending' and self.status == 'approved') or 
            (is_new_instance and auto_approved and self.status == 'approved')):
            try:
                from apps.operations.tasks import process_account_creation
                process_account_creation.delay(self.pk)
            except Exception as e:
                logger.error(f"Failed to dispatch account creation task for request {self.pk}: {str(e)}")

    def auto_process_creation(self):
        """审批通过后自动创建用户"""
        from django.db import transaction
        import os

        product = self.target_product
        if not product:
            logger.error(f"AccountOpeningRequest {self.id} has no target_product")
            return
        
        host = product.host

        user_disk_quota = {}
        if product.enable_disk_quota and product.default_disk_quota:
            user_disk_quota = dict(product.default_disk_quota)
            if self.requested_disk_capacity:
                for disk, capacity in self.requested_disk_capacity.items():
                    if disk in product.allow_extra_quota_disks:
                        user_disk_quota[disk] = capacity

        # DEMO模式
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info(f'DEMO模式: 模拟创建用户 {self.username}')
            password = CloudComputerUser.generate_complex_password()

            with transaction.atomic():
                self.status = 'completed'
                self.result_message = f"用户 {self.username} 已在DEMO模式下创建（模拟）"
                self.save(update_fields=['status', 'result_message'])

                CloudComputerUser.objects.get_or_create(
                    username=self.username,
                    product=self.target_product,
                    defaults={
                        'fullname': self.user_fullname,
                        'email': self.user_email,
                        'description': self.user_description,
                        'created_from_request': self,
                        'owner': self.applicant,
                        'initial_password': password,
                        'disk_quota': user_disk_quota,
                    }
                )
            return

        # 正式模式
        try:
            from utils.winrm_client import WinrmClient

            client = WinrmClient(
                hostname=host.hostname,
                port=host.port,
                username=host.username,
                password=host.password,
                use_ssl=host.use_ssl
            )

            password = CloudComputerUser.generate_complex_password()
            result = client.create_user(
                username=self.username,
                password=password,
                description=self.user_description
            )

            if result.status_code == 0:
                if user_disk_quota:
                    try:
                        from utils.disk_quota import set_user_disk_quotas
                        quota_result = set_user_disk_quotas(
                            client, self.username, user_disk_quota
                        )
                        if not quota_result['success']:
                            logger.warning(
                                f"用户 {self.username} 磁盘配额设置部分失败: "
                                f"{quota_result.get('errors', [])}"
                            )
                    except Exception as e:
                        logger.error(
                            f"用户 {self.username} 磁盘配额设置失败: {str(e)}"
                        )

                # 远程成功后，事务写本地
                with transaction.atomic():
                    self.status = 'completed'
                    self.result_message = f"用户 {self.username} 已成功创建"
                    self.save(update_fields=['status', 'result_message'])

                    CloudComputerUser.objects.get_or_create(
                        username=self.username,
                        product=self.target_product,
                        defaults={
                            'fullname': self.user_fullname,
                            'email': self.user_email,
                            'description': self.user_description,
                            'created_from_request': self,
                            'owner': self.applicant,
                            'initial_password': password,
                            'disk_quota': user_disk_quota,
                        }
                    )
            else:
                error_msg = result.std_err or '未知错误'
                self.status = 'failed'
                self.result_message = f"创建用户失败: {error_msg}"
                self.save(update_fields=['status', 'result_message'])

        except Exception as e:
            self.status = 'failed'
            self.result_message = f"处理异常: {str(e)}"
            self.save(update_fields=['status', 'result_message'])


class CloudComputerUser(models.Model):
    """
    云电脑用户模型

    记录在各个云电脑产品上创建的用户信息
    """
    # 用户信息
    username = models.CharField(
        max_length=150,
        verbose_name=_('用户名'),
        help_text=_('在云电脑上的用户名')
    )
    fullname = models.CharField(
        max_length=200,
        verbose_name=_('用户姓名'),
        help_text=_('用户真实姓名')
    )
    email = models.EmailField(
        verbose_name=_('用户邮箱'),
        help_text=_('用户邮箱地址')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('用户描述'),
        help_text=_('关于该用户的附加信息')
    )

    # 关联的产品（替代原来的host）
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name=_('所属产品'),
        help_text=_('该用户所属的云电脑产品')
    )

    # 状态信息
    status = models.CharField(
        max_length=20,
        choices=[
            ('active', _('激活')),
            ('inactive', _('未激活')),
            ('disabled', _('已禁用')),
            ('deleted', _('已删除')),
        ],
        default='active',
        verbose_name=_('用户状态'),
        help_text=_('用户在云电脑上的状态')
    )

    # 权限信息
    is_admin = models.BooleanField(
        default=False,
        verbose_name=_('管理员权限'),
        help_text=_('是否具有管理员权限')
    )
    groups = models.TextField(
        blank=True,
        verbose_name=_('用户组'),
        help_text=_('用户所属的组（逗号分隔）')
    )

    disk_quota = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('磁盘配额'),
        help_text=_('用户的磁盘配额配置（MB），如 {"C:": 10240, "D:": 20480}')
    )

    # 创建信息
    created_from_request = models.ForeignKey(
        AccountOpeningRequest,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('来源申请'),
        help_text=_('创建此用户的开户申请')
    )
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cloud_users',
        verbose_name=_('所有者'),
        help_text=_('拥有此云电脑账户的用户')
    )
    
    # 密码信息（临时存储）
    _initial_password = models.CharField(
        max_length=512,
        blank=True,
        db_column='initial_password',
        verbose_name=_('初始密码(加密)'),
        help_text=_('用户的初始密码(加密存储)，查看后将被清除')
    )

    @property
    def initial_password(self):
        if not self._initial_password:
            return ''
        try:
            return _get_fernet().decrypt(self._initial_password.encode()).decode()
        except Exception:
            raise ValueError("密码解密失败，数据可能已损坏或密钥已变更")

    @initial_password.setter
    def initial_password(self, value):
        if value:
            self._initial_password = _get_fernet().encrypt(value.encode()).decode()
        else:
            self._initial_password = ''
    password_viewed = models.BooleanField(
        default=False,
        verbose_name=_('密码已查看'),
        help_text=_('指示初始密码是否已被查看')
    )
    password_viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('密码查看时间'),
        help_text=_('初始密码被查看的时间')
    )

    # 时间信息
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间'),
        help_text=_('用户在云电脑上创建的时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间'),
        help_text=_('信息最后更新时间')
    )

    class Meta:
        verbose_name = _('云电脑用户')
        verbose_name_plural = _('云电脑用户')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['product']),
            models.Index(fields=['username']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
        unique_together = [['product', 'username']]  # 确保同一产品上用户名唯一

    def __str__(self):
        return f'{self.username}@{self.product.display_name}'

    def activate(self):
        """
        激活用户
        """
        self.status = 'active'
        self.save(update_fields=['status', 'updated_at'])

    def deactivate(self):
        """
        禁用用户
        """
        self.status = 'inactive'
        self.save(update_fields=['status', 'updated_at'])

    def disable(self):
        """
        删除用户
        """
        self.status = 'disabled'
        self.save(update_fields=['status', 'updated_at'])

    def delete_user(self):
        """
        标记用户为已删除
        """
        self.status = 'deleted'
        self.save(update_fields=['status', 'updated_at'])

    def save(self, *args, **kwargs):
        """
        重写save方法，当状态改变时通过Celery异步执行远程操作
        """
        old_status = None
        if self.pk:
            try:
                old_status = CloudComputerUser.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            except Exception:
                pass

        super().save(*args, **kwargs)

        if old_status is not None:
            remote_action = None
            if old_status != 'disabled' and self.status == 'disabled':
                remote_action = 'disable'
            elif old_status == 'disabled' and self.status == 'active':
                remote_action = 'enable'
            elif old_status != 'deleted' and self.status == 'deleted':
                remote_action = 'delete'

            if remote_action:
                try:
                    from apps.operations.tasks import execute_cloud_user_remote_action
                    execute_cloud_user_remote_action.delay(self.pk, remote_action)
                except Exception as e:
                    logger.error(f"Failed to dispatch remote action '{remote_action}' for user {self.username}: {str(e)}")

    def disable_remote_user(self):
        import os
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info(f'DEMO模式: 模拟禁用用户 {self.username} 在产品 {self.product.display_name}')
            return
        
        try:
            from utils.winrm_client import WinrmClient
            
            product = self.product
            host = product.host
            client = WinrmClient(
                hostname=host.hostname,
                port=host.port,
                username=host.username,
                password=host.password,
                use_ssl=host.use_ssl
            )
            
            result = client.disabled_user(self.username)
            if result.status_code != 0:
                error_msg = result.std_err if result.std_err else 'Unknown error'
                logger.error(f"Failed to disable user {self.username} on host {host.name}: {error_msg}")
        except Exception as e:
            logger.error(f"Error disabling user {self.username} on host {host.name}: {str(e)}")

    def enable_remote_user(self):
        import os
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info(f'DEMO模式: 模拟启用用户 {self.username} 在产品 {self.product.display_name}')
            return
        
        try:
            from utils.winrm_client import WinrmClient
            
            product = self.product
            host = product.host
            client = WinrmClient(
                hostname=host.hostname,
                port=host.port,
                username=host.username,
                password=host.password,
                use_ssl=host.use_ssl
            )
            
            result = client.enable_user(self.username)
            if result.status_code != 0:
                error_msg = result.std_err if result.std_err else 'Unknown error'
                logger.error(f"Failed to enable user {self.username} on host {host.name}: {error_msg}")
        except Exception as e:
            logger.error(f"Error enabling user {self.username} on host {host.name}: {str(e)}")

    def delete_remote_user(self):
        import os
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info(f'DEMO模式: 模拟删除用户 {self.username} 在产品 {self.product.display_name}')
            return
        
        try:
            from utils.winrm_client import WinrmClient
            
            product = self.product
            host = product.host
            client = WinrmClient(
                hostname=host.hostname,
                port=host.port,
                username=host.username,
                password=host.password,
                use_ssl=host.use_ssl
            )
            
            result = client.delete_user(self.username)
            if result.status_code != 0:
                error_msg = result.std_err if result.std_err else 'Unknown error'
                logger.error(f"Failed to delete user {self.username} on host {host.name}: {error_msg}")
        except Exception as e:
            logger.error(f"Error deleting user {self.username} on host {host.name}: {str(e)}")

    def get_and_burn_password(self):
        from django.utils import timezone

        if self.password_viewed:
            raise Exception('密码已被查看，无法再次获取。如需重置请联系管理员。')

        if not self._initial_password:
            raise Exception('密码不存在')

        password = self.initial_password
        self.password_viewed = True
        self.password_viewed_at = timezone.now()
        self.initial_password = ''
        self.save(update_fields=['password_viewed', 'password_viewed_at', '_initial_password'])
        return password

    def reset_windows_password(self, new_password):
        import os
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info(f'DEMO模式: 模拟重置用户 {self.username} 的密码')
            return
        
        try:
            from utils.winrm_client import WinrmClient
            
            product = self.product
            host = product.host
            client = WinrmClient(
                hostname=host.hostname,
                port=host.port,
                username=host.username,
                password=host.password,
                use_ssl=host.use_ssl
            )
            
            result = client.reset_password(self.username, new_password)
            if result.status_code != 0:
                error_msg = result.std_err if result.std_err else 'Unknown error'
                logger.error(f"Failed to reset password for user {self.username} on host {host.name}: {error_msg}")
        except Exception as e:
            logger.error(f"Error resetting password for user {self.username} on host {host.name}: {str(e)}")

    @staticmethod
    def generate_complex_password(length=16):
        """
        生成复杂密码
        
        Args:
            length: 密码长度，默认为16位
        
        Returns:
            生成的复杂密码
        """
        import secrets
        import string
        
        # 包含大写字母、小写字母、数字和特殊字符
        alphabet = string.ascii_letters + string.digits + '!@#$%^&*()_+-=[]{}|;:,.<>?'
        
        # 确保至少包含每种类型的字符
        while True:
            password = ''.join(secrets.choice(alphabet) for i in range(length))
            
            # 检查是否包含所需类型的字符
            has_upper = any(c.isupper() for c in password)
            has_lower = any(c.islower() for c in password)
            has_digit = any(c.isdigit() for c in password)
            has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
            
            if has_upper and has_lower and has_digit and has_special:
                return password


class RdpDomainRoute(models.Model):
    """
    RDP域名路由（SNI路由已弃用，现使用RD Gateway + tunnel_token路由）
    domain字段仅用于显示和追踪，不再用于SNI路由
    """
    domain = models.CharField(
        max_length=255, unique=True,
        verbose_name=_('RDP域名'),
        help_text=_('分配给用户的临时RDP访问域名（仅用于显示/追踪，不再用于SNI路由）')
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        verbose_name=_('关联产品'),
        help_text=_('此域名关联的云电脑产品')
    )
    assigned_to = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name=_('分配用户'),
        help_text=_('被分配此RDP域名的用户')
    )
    tunnel_token = models.CharField(
        max_length=64, blank=True,
        verbose_name=_('隧道Token'),
        help_text=_('关联主机的隧道Token，用于RD Gateway路由')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('是否有效'),
        help_text=_('域名是否仍然有效')
    )
    expires_at = models.DateTimeField(
        verbose_name=_('过期时间'),
        help_text=_('域名过期时间，10分钟无连接后过期')
    )
    last_activity_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('最后活动时间'),
        help_text=_('最后一次RDP连接活动时间')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )

    class Meta:
        verbose_name = _('RDP域名路由')
        verbose_name_plural = _('RDP域名路由')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['domain']),
            models.Index(fields=['is_active']),
            models.Index(fields=['assigned_to']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['product']),
        ]

    def __str__(self):
        status = '有效' if self.is_active else '已过期'
        return f'{self.domain} -> {self.product.display_name} ({status})'

    @staticmethod
    def generate_domain():
        import secrets
        import string
        prefix = ''.join(
            secrets.choice(string.ascii_lowercase + string.digits)
            for _ in range(8)
        )
        from django.conf import settings as django_settings
        base_domain = getattr(
            django_settings, 'RDP_DOMAIN', '2c2a.com'
        )
        return f'rdp-{prefix}.{base_domain}'

    def is_expired(self):
        return timezone.now() > self.expires_at

    def deactivate(self):
        self.is_active = False
        self.save(update_fields=['is_active'])

    @property
    def is_protected(self):
        return self.product.enable_host_protection


class ProductInvitationToken(models.Model):
    """
    产品邀请令牌模型

    用于生成邀请链接，用户访问链接后可解锁指定产品或产品组的访问权限
    """
    token = models.CharField(
        max_length=64,
        unique=True,
        verbose_name=_('邀请令牌'),
        help_text=_('用于邀请链接的唯一令牌')
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='invitation_tokens',
        verbose_name=_('关联产品'),
        help_text=_('此令牌关联的产品（与产品组至少选一个）')
    )
    product_group = models.ForeignKey(
        ProductGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='invitation_tokens',
        verbose_name=_('关联产品组'),
        help_text=_('此令牌关联的产品组（与产品至少选一个）')
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_invitation_tokens',
        verbose_name=_('创建者'),
        help_text=_('创建此邀请令牌的用户')
    )
    max_uses = models.IntegerField(
        default=0,
        verbose_name=_('最大使用次数'),
        help_text=_('令牌最大可使用次数，0表示无限制')
    )
    used_count = models.IntegerField(
        default=0,
        verbose_name=_('已使用次数'),
        help_text=_('令牌已被使用的次数')
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('过期时间'),
        help_text=_('令牌过期时间，留空表示永不过期')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('是否启用'),
        help_text=_('令牌是否有效')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_('更新时间')
    )

    class Meta:
        verbose_name = _('产品邀请令牌')
        verbose_name_plural = _('产品邀请令牌')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['is_active']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        target = self.product.display_name if self.product else (self.product_group.name if self.product_group else _('未知'))
        return f'{self.token[:8]}... -> {target}'

    def is_expired(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    def is_exhausted(self):
        if self.max_uses > 0 and self.used_count >= self.max_uses:
            return True
        return False

    def is_valid(self):
        return self.is_active and not self.is_expired() and not self.is_exhausted()

    def increment_usage(self):
        from django.db.models import F
        self.used_count = F('used_count') + 1
        self.save(update_fields=['used_count', 'updated_at'])
        self.refresh_from_db()

    def generate_token(self):
        import secrets
        import string
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = self.generate_token()
        super().save(*args, **kwargs)


class ProductAccessGrant(models.Model):
    """
    产品访问授权记录模型

    记录用户通过邀请链接获得的产品或产品组访问权限
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='product_access_grants',
        verbose_name=_('用户'),
        help_text=_('获得访问权限的用户')
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='access_grants',
        verbose_name=_('关联产品'),
        help_text=_('授权访问的产品')
    )
    product_group = models.ForeignKey(
        ProductGroup,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='access_grants',
        verbose_name=_('关联产品组'),
        help_text=_('授权访问的产品组')
    )
    granted_by_token = models.ForeignKey(
        ProductInvitationToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='access_grants',
        verbose_name=_('来源邀请令牌'),
        help_text=_('通过哪个邀请令牌获得的权限')
    )
    granted_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('授权时间')
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('授权过期时间'),
        help_text=_('访问权限过期时间，留空表示永久有效')
    )
    is_revoked = models.BooleanField(
        default=False,
        verbose_name=_('是否已撤销'),
        help_text=_('权限是否已被撤销')
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('撤销时间')
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='revoked_access_grants',
        verbose_name=_('撤销人'),
        help_text=_('撤销此权限的用户')
    )

    class Meta:
        verbose_name = _('产品访问授权')
        verbose_name_plural = _('产品访问授权')
        ordering = ['-granted_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['product']),
            models.Index(fields=['product_group']),
            models.Index(fields=['is_revoked']),
            models.Index(fields=['granted_at']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'product'],
                condition=models.Q(product__isnull=False),
                name='unique_user_product_grant'
            ),
            models.UniqueConstraint(
                fields=['user', 'product_group'],
                condition=models.Q(product_group__isnull=False),
                name='unique_user_productgroup_grant'
            ),
        ]

    def __str__(self):
        target = self.product.display_name if self.product else (self.product_group.name if self.product_group else _('未知'))
        status = _('已撤销') if self.is_revoked else (_('已过期') if self.is_expired() else _('有效'))
        return f'{self.user.username} -> {target} ({status})'

    def is_expired(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return True
        return False

    def is_effective(self):
        return not self.is_revoked and not self.is_expired()
