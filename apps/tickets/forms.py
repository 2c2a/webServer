"""
工单系统表单
"""
from django import forms
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from .models import Ticket, TicketComment, TicketCategory
from apps.accounts.models import UserBan

User = get_user_model()


MD3_INPUT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 '
    'text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 '
    'focus:ring-md-primary transition'
)


class TicketForm(forms.ModelForm):
    """
    工单创建/编辑表单
    """
    title = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': MD3_INPUT_CLASS,
            'placeholder': '请输入工单标题'
        }),
        label=_('标题'),
        help_text=_('请简要描述工单主题')
    )

    description = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': MD3_INPUT_CLASS,
            'rows': 6,
            'placeholder': '请详细描述您的问题或需求'
        }),
        label=_('详细描述'),
        help_text=_('请提供尽可能详细的信息，以便我们更好地帮助您')
    )

    category = forms.ModelChoiceField(
        queryset=TicketCategory.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': MD3_INPUT_CLASS}),
        label=_('分类'),
        help_text=_('请选择工单分类'),
        required=False
    )

    priority = forms.ChoiceField(
        choices=Ticket.PRIORITY_CHOICES,
        widget=forms.Select(attrs={'class': MD3_INPUT_CLASS}),
        label=_('优先级'),
        help_text=_('请选择工单优先级'),
        initial='medium'
    )

    related_cloud_computer = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={'class': MD3_INPUT_CLASS}),
        label=_('关联云电脑'),
        help_text=_('选择您拥有的云电脑（可选）'),
        required=False
    )

    related_request = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={'class': MD3_INPUT_CLASS}),
        label=_('关联申请'),
        help_text=_('选择您提交的申请（可选）'),
        required=False
    )

    class Meta:
        model = Ticket
        fields = ['title', 'description', 'category', 'priority', 'related_cloud_computer', 'related_request']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        from apps.operations.models import CloudComputerUser, AccountOpeningRequest

        # 关联云电脑：只显示当前用户拥有的、激活状态的云电脑
        if self.user:
            self.fields['related_cloud_computer'].queryset = CloudComputerUser.objects.filter(
                owner=self.user, status='active'
            ).select_related('product')
            # 关联申请：只显示当前用户提交的申请
            self.fields['related_request'].queryset = AccountOpeningRequest.objects.filter(
                applicant=self.user
            ).select_related('target_product').order_by('-created_at')
        else:
            self.fields['related_cloud_computer'].queryset = CloudComputerUser.objects.none()
            self.fields['related_request'].queryset = AccountOpeningRequest.objects.none()

        # 封禁用户只能选择允许封禁用户提交的分类
        if self.user and UserBan.objects.filter(user=self.user).exists():
            self.fields['category'].queryset = TicketCategory.objects.filter(
                is_active=True, allow_banned_users=True
            )
            # 封禁用户不需要关联云电脑和申请
            self.fields['related_cloud_computer'].queryset = CloudComputerUser.objects.none()
            self.fields['related_request'].queryset = AccountOpeningRequest.objects.none()
        
        # 如果有分类，设置默认优先级
        if self.data.get('category'):
            try:
                category = TicketCategory.objects.get(pk=self.data['category'])
                self.fields['priority'].initial = category.default_priority
            except TicketCategory.DoesNotExist:
                pass

    def clean(self):
        cleaned_data = super().clean()
        
        # 如果有分类，继承分类的默认优先级（如果用户未修改）
        category = cleaned_data.get('category')
        priority = cleaned_data.get('priority')
        
        if category and priority == 'medium' and category.default_priority != 'medium':
            # 如果用户没有显式修改优先级，使用分类默认值
            if not self.data.get('priority') or self.data.get('priority') == 'medium':
                cleaned_data['priority'] = category.default_priority
        
        return cleaned_data


class TicketCommentForm(forms.ModelForm):
    """
    工单评论表单
    """
    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': '请输入评论内容'
        }),
        label=_('内容'),
        help_text=_('请输入您的回复')
    )
    
    is_internal = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        label=_('内部备注'),
        help_text=_('仅工作人员可见')
    )

    class Meta:
        model = TicketComment
        fields = ['content', 'is_internal']


class TicketAssignForm(forms.Form):
    """
    工单分配表单
    """
    assignee = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('处理人'),
        help_text=_('请选择要分配的处理人'),
        required=False,
    )

    assigned_group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('处理组'),
        help_text=_('请选择要分配的处理组'),
        required=False,
    )

    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': '可选：添加分配备注'
        }),
        label=_('备注'),
        help_text=_('可选：添加分配备注')
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assignee'].queryset = User.objects.filter(
            is_active=True
        ).filter(
            models.Q(is_staff=True) | models.Q(is_superuser=True) | models.Q(groups__name='主机提供商')
        ).distinct()

    def clean(self):
        cleaned_data = super().clean()
        assignee = cleaned_data.get('assignee')
        assigned_group = cleaned_data.get('assigned_group')
        if not assignee and not assigned_group:
            raise forms.ValidationError(_('请至少选择一个处理人或处理组'))
        return cleaned_data


class TicketStatusForm(forms.Form):
    """
    工单状态变更表单
    """
    status = forms.ChoiceField(
        choices=[
            ('pending', _('待处理')),
            ('processing', _('处理中')),
            ('waiting_feedback', _('待反馈')),
            ('resolved', _('已解决')),
            ('closed', _('已关闭')),
            ('rejected', _('已驳回')),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('新状态'),
        help_text=_('请选择新的工单状态')
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': '可选：添加状态变更备注'
        }),
        label=_('备注'),
        help_text=_('可选：添加状态变更备注')
    )


class TicketCloseForm(forms.Form):
    """
    工单关闭表单（含满意度评价）
    """
    satisfaction = forms.ChoiceField(
        required=False,
        choices=[
            ('', _('不评价')),
            ('5', _('非常满意')),
            ('4', _('满意')),
            ('3', _('一般')),
            ('2', _('不满意')),
            ('1', _('非常不满意')),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('满意度评分'),
        help_text=_('请对工单处理进行评价')
    )
    
    satisfaction_comment = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': '可选：请输入您的评价内容'
        }),
        label=_('评价内容'),
        help_text=_('可选：请输入您的评价内容')
    )


class TicketFilterForm(forms.Form):
    """
    工单筛选表单
    """
    status = forms.ChoiceField(
        required=False,
        choices=[('', _('全部'))] + Ticket.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('状态')
    )
    
    priority = forms.ChoiceField(
        required=False,
        choices=[('', _('全部'))] + Ticket.PRIORITY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('优先级')
    )
    
    category = forms.ModelChoiceField(
        required=False,
        queryset=TicketCategory.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label=_('分类')
    )
    
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '搜索工单编号、标题或描述'
        }),
        label=_('搜索')
    )
    
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label=_('开始日期')
    )
    
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date'
        }),
        label=_('结束日期')
    )
