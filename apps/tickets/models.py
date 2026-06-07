"""
工单系统模型
"""
import os
import secrets
import string
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django.dispatch import Signal

User = get_user_model()

# 定义工单信号
ticket_created = Signal()
ticket_assigned = Signal()
ticket_status_changed = Signal()
ticket_closed = Signal()
ticket_comment_added = Signal()


def generate_ticket_no():
    """
    生成工单编号
    格式: T + 年月日 + 4位随机字符
    """
    date_str = timezone.now().strftime('%Y%m%d')
    random_str = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(4))
    return f"T{date_str}{random_str}"


class TicketCategory(models.Model):
    """
    工单分类模型
    """
    name = models.CharField(
        max_length=100,
        verbose_name=_('分类名称'),
        help_text=_('工单分类的名称')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('分类描述'),
        help_text=_('分类的详细描述')
    )
    icon = models.CharField(
        max_length=50,
        blank=True,
        default='help_outline',
        verbose_name=_('图标'),
        help_text=_('Material Icons 图标名称')
    )
    default_priority = models.CharField(
        max_length=20,
        choices=[
            ('urgent', _('紧急')),
            ('high', _('高')),
            ('medium', _('中')),
            ('low', _('低')),
        ],
        default='medium',
        verbose_name=_('默认优先级'),
        help_text=_('该分类下工单的默认优先级')
    )
    auto_assign_to = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auto_assigned_categories',
        verbose_name=_('自动分配给'),
        help_text=_('该分类的工单自动分配给指定用户')
    )
    auto_assign_to_group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auto_assigned_categories',
        verbose_name=_('自动分配给用户组'),
        help_text=_('该分类的工单自动分配给指定用户组')
    )
    sla_hours = models.PositiveIntegerField(
        default=24,
        verbose_name=_('SLA时限(小时)'),
        help_text=_('工单处理的服务级别协议时限')
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_('是否启用'),
        help_text=_('是否在前端展示此分类')
    )
    allow_banned_users = models.BooleanField(
        default=False,
        verbose_name=_('允许封禁用户提交'),
        help_text=_('封禁用户是否可以在此分类下提交工单')
    )
    display_order = models.IntegerField(
        default=0,
        verbose_name=_('显示顺序'),
        help_text=_('分类在前端展示的顺序，数字越小越靠前')
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_ticket_categories',
        verbose_name=_('创建者'),
        help_text=_('创建此分类的用户，用于提供商数据隔离')
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
        verbose_name = _('工单分类')
        verbose_name_plural = _('工单分类')
        ordering = ['display_order', 'name']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['display_order']),
        ]

    def __str__(self):
        return self.name


class Ticket(models.Model):
    """
    工单模型
    """
    STATUS_CHOICES = [
        ('pending', _('待处理')),
        ('processing', _('处理中')),
        ('waiting_feedback', _('待反馈')),
        ('resolved', _('已解决')),
        ('closed', _('已关闭')),
        ('rejected', _('已驳回')),
    ]

    PRIORITY_CHOICES = [
        ('urgent', _('紧急')),
        ('high', _('高')),
        ('medium', _('中')),
        ('low', _('低')),
    ]

    SOURCE_CHOICES = [
        ('web', _('Web提交')),
        ('api', _('API创建')),
        ('system', _('系统自动生成')),
        ('email', _('邮件导入')),
    ]

    ticket_no = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_('工单编号'),
        help_text=_('自动生成的唯一工单编号')
    )
    title = models.CharField(
        max_length=200,
        verbose_name=_('标题'),
        help_text=_('工单的简要标题')
    )
    description = models.TextField(
        verbose_name=_('详细描述'),
        help_text=_('工单的详细描述')
    )
    category = models.ForeignKey(
        TicketCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name=_('分类'),
        help_text=_('工单所属的分类')
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name=_('状态'),
        help_text=_('工单的当前状态')
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_CHOICES,
        default='medium',
        verbose_name=_('优先级'),
        help_text=_('工单的优先级')
    )
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES,
        default='web',
        verbose_name=_('来源'),
        help_text=_('工单的创建来源')
    )
    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_tickets',
        verbose_name=_('创建者'),
        help_text=_('提交工单的用户')
    )
    assignee = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
        verbose_name=_('处理人'),
        help_text=_('负责处理此工单的用户')
    )
    assigned_group = models.ForeignKey(
        Group,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tickets',
        verbose_name=_('处理组'),
        help_text=_('负责处理此工单的用户组')
    )
    related_product = models.ForeignKey(
        'operations.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name=_('关联产品'),
        help_text=_('工单关联的云电脑产品')
    )
    related_host = models.ForeignKey(
        'hosts.Host',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name=_('关联主机'),
        help_text=_('工单关联的主机')
    )
    due_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('截止时间'),
        help_text=_('根据SLA计算的工单处理截止时间')
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('解决时间'),
        help_text=_('工单被标记为已解决的时间')
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('关闭时间'),
        help_text=_('工单被关闭的时间')
    )
    satisfaction = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name=_('满意度评分'),
        help_text=_('用户对工单处理的满意度评分（1-5）')
    )
    satisfaction_comment = models.TextField(
        blank=True,
        verbose_name=_('满意度评价'),
        help_text=_('用户对工单处理的评价内容')
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
        verbose_name = _('工单')
        verbose_name_plural = _('工单')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ticket_no']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['assignee']),
            models.Index(fields=['assigned_group']),
            models.Index(fields=['creator']),
            models.Index(fields=['category']),
            models.Index(fields=['created_at']),
            models.Index(fields=['due_at']),
        ]

    def __str__(self):
        return f"[{self.ticket_no}] {self.title}"

    def save(self, *args, **kwargs):
        """
        重写save方法，自动生成工单编号，计算SLA截止时间
        """
        is_new = not self.pk
        
        if is_new and not self.ticket_no:
            # 确保工单编号唯一
            while True:
                ticket_no = generate_ticket_no()
                if not Ticket.objects.filter(ticket_no=ticket_no).exists():
                    self.ticket_no = ticket_no
                    break
        
        # 计算SLA截止时间
        if is_new and self.category and self.category.sla_hours and not self.due_at:
            self.due_at = timezone.now() + timezone.timedelta(hours=self.category.sla_hours)
        
        # 记录状态变更前的旧状态
        old_status = None
        old_assignee_id = None
        old_assigned_group_id = None
        if self.pk:
            try:
                old_ticket = Ticket.objects.get(pk=self.pk)
                old_status = old_ticket.status
                old_assignee_id = old_ticket.assignee_id
                old_assigned_group_id = old_ticket.assigned_group_id
            except Ticket.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
        
        # 发送信号
        if is_new:
            ticket_created.send(sender=self.__class__, instance=self)
        
        if old_status and old_status != self.status:
            ticket_status_changed.send(
                sender=self.__class__, 
                instance=self, 
                old_status=old_status, 
                new_status=self.status
            )
            
            # 记录活动
            TicketActivity.objects.create(
                ticket=self,
                actor=self.creator if hasattr(self, '_current_user') else None,
                action='status_change',
                old_value=old_status,
                new_value=self.status,
                description=f'状态从 "{self.get_status_display_old(old_status)}" 变更为 "{self.get_status_display()}"'
            )
        
        if old_assignee_id != self.assignee_id or old_assigned_group_id != self.assigned_group_id:
            assign_desc_parts = []
            if self.assignee:
                assign_desc_parts.append(f'用户 {self.assignee.username}')
            if self.assigned_group:
                assign_desc_parts.append(f'用户组 {self.assigned_group.name}')
            if assign_desc_parts:
                ticket_assigned.send(sender=self.__class__, instance=self)
                TicketActivity.objects.create(
                    ticket=self,
                    actor=self.creator if hasattr(self, '_current_user') else None,
                    action='assign',
                    new_value=' / '.join(assign_desc_parts),
                    description=f'工单分配给 {" / ".join(assign_desc_parts)}'
                )

    def get_status_display_old(self, status):
        """获取指定状态的显示文本"""
        for code, name in self.STATUS_CHOICES:
            if code == status:
                return name
        return status

    def assign_to(self, user=None, group=None, actor=None):
        """
        分配工单给指定用户和/或用户组
        """
        if user is not None:
            self.assignee = user
        if group is not None:
            self.assigned_group = group
        if actor:
            self._current_user = actor
        self.save()

    def update_status(self, new_status, actor=None, notes=''):
        """
        更新工单状态
        """
        if new_status not in [s[0] for s in self.STATUS_CHOICES]:
            raise ValueError(f'无效的状态: {new_status}')
        
        self.status = new_status
        
        if new_status == 'resolved':
            self.resolved_at = timezone.now()
        elif new_status == 'closed':
            self.closed_at = timezone.now()
        
        if actor:
            self._current_user = actor
        self.save()

    def close(self, actor=None, satisfaction=None, comment=''):
        """
        关闭工单
        """
        self.status = 'closed'
        self.closed_at = timezone.now()
        if satisfaction is not None:
            self.satisfaction = satisfaction
        if comment:
            self.satisfaction_comment = comment
        if actor:
            self._current_user = actor
        self.save()
        ticket_closed.send(sender=self.__class__, instance=self)

    def is_overdue(self):
        """
        检查工单是否已超时
        """
        if self.due_at and self.status not in ['resolved', 'closed', 'rejected']:
            return timezone.now() > self.due_at
        return False

    @property
    def assignee_display(self):
        """
        获取处理人显示文本（包含用户和用户组）
        """
        parts = []
        if self.assignee:
            parts.append(self.assignee.username)
        if self.assigned_group:
            parts.append(f'{self.assigned_group.name}(组)')
        return ' / '.join(parts) if parts else None

    @property
    def status_badge_class(self):
        """
        获取状态对应的Bootstrap徽章样式类
        """
        badge_map = {
            'pending': 'bg-secondary',
            'processing': 'bg-primary',
            'waiting_feedback': 'bg-warning',
            'resolved': 'bg-success',
            'closed': 'bg-dark',
            'rejected': 'bg-danger',
        }
        return badge_map.get(self.status, 'bg-secondary')

    @property
    def priority_badge_class(self):
        """
        获取优先级对应的Bootstrap徽章样式类
        """
        badge_map = {
            'urgent': 'bg-danger',
            'high': 'bg-warning',
            'medium': 'bg-info',
            'low': 'bg-success',
        }
        return badge_map.get(self.priority, 'bg-info')


class TicketComment(models.Model):
    """
    工单评论/回复模型
    """
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='comments',
        verbose_name=_('关联工单'),
        help_text=_('评论所属的工单')
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ticket_comments',
        verbose_name=_('作者'),
        help_text=_('评论的作者')
    )
    content = models.TextField(
        verbose_name=_('内容'),
        help_text=_('评论的详细内容')
    )
    is_internal = models.BooleanField(
        default=False,
        verbose_name=_('内部备注'),
        help_text=_('是否为仅工作人员可见的内部备注')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )

    class Meta:
        verbose_name = _('工单评论')
        verbose_name_plural = _('工单评论')
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
        ]

    def __str__(self):
        return f'{self.author.username} - {self.ticket.ticket_no}'

    def save(self, *args, **kwargs):
        is_new = not self.pk
        super().save(*args, **kwargs)
        if is_new:
            ticket_comment_added.send(sender=self.__class__, instance=self)
            # 记录活动
            TicketActivity.objects.create(
                ticket=self.ticket,
                actor=self.author,
                action='comment',
                description=f'{"添加内部备注" if self.is_internal else "添加评论"}'
            )


class TicketActivity(models.Model):
    """
    工单活动记录模型
    """
    ACTION_CHOICES = [
        ('create', _('创建')),
        ('assign', _('分配')),
        ('status_change', _('状态变更')),
        ('comment', _('评论')),
        ('close', _('关闭')),
        ('update', _('更新')),
    ]

    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='activities',
        verbose_name=_('关联工单'),
        help_text=_('活动所属的工单')
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ticket_activities',
        verbose_name=_('操作人'),
        help_text=_('执行此操作的用户')
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name=_('操作类型'),
        help_text=_('活动的操作类型')
    )
    old_value = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('旧值'),
        help_text=_('变更前的值')
    )
    new_value = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('新值'),
        help_text=_('变更后的值')
    )
    description = models.TextField(
        blank=True,
        verbose_name=_('描述'),
        help_text=_('活动的详细描述')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )

    class Meta:
        verbose_name = _('工单活动')
        verbose_name_plural = _('工单活动')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ticket', 'created_at']),
        ]

    def __str__(self):
        actor_name = self.actor.username if self.actor else _('系统')
        return f'[{actor_name}] {self.get_action_display()} - {self.ticket.ticket_no}'


class TicketAttachment(models.Model):
    """
    工单附件模型
    """
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name=_('关联工单'),
        help_text=_('附件所属的工单')
    )
    file = models.FileField(
        upload_to='ticket_attachments/%Y/%m/',
        verbose_name=_('文件'),
        help_text=_('上传的附件文件')
    )
    filename = models.CharField(
        max_length=255,
        verbose_name=_('原始文件名'),
        help_text=_('文件的原始名称')
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='ticket_attachments',
        verbose_name=_('上传人'),
        help_text=_('上传此附件的用户')
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('创建时间')
    )

    class Meta:
        verbose_name = _('工单附件')
        verbose_name_plural = _('工单附件')
        ordering = ['-created_at']

    def __str__(self):
        return self.filename

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
        super().save(*args, **kwargs)
