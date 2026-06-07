"""
工单系统 - 超管后台表单

超管可管理所有数据，无数据隔离。
"""

from django import forms
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _

from .models import TicketCategory, TicketComment


class AdminTicketCategoryForm(forms.ModelForm):
    """
    工单分类表单（超管后台）

    超管可设置 auto_assign_to 字段，created_by 在视图中自动设置。
    """

    name = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface '
                     'placeholder-md-outline focus:outline-none '
                     'focus:ring-2 focus:ring-md-primary transition',
            'placeholder': '请输入分类名称',
        }),
        label=_('分类名称'),
    )

    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface '
                     'placeholder-md-outline focus:outline-none '
                     'focus:ring-2 focus:ring-md-primary transition resize-y',
            'rows': 3,
            'placeholder': '请输入分类描述（可选）',
        }),
        label=_('分类描述'),
    )

    icon = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface '
                     'placeholder-md-outline focus:outline-none '
                     'focus:ring-2 focus:ring-md-primary transition',
            'placeholder': 'Material Icons 图标名称，如 help_outline',
        }),
        label=_('图标'),
    )

    default_priority = forms.ChoiceField(
        choices=TicketCategory._meta.get_field('default_priority').choices,
        widget=forms.Select(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface appearance-none '
                     'focus:outline-none focus:ring-2 focus:ring-md-primary '
                     'transition cursor-pointer',
        }),
        label=_('默认优先级'),
    )

    auto_assign_to = forms.ModelChoiceField(
        required=False,
        queryset=None,
        widget=forms.Select(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface appearance-none '
                     'focus:outline-none focus:ring-2 focus:ring-md-primary '
                     'transition cursor-pointer',
        }),
        label=_('自动分配给'),
        help_text=_('该分类的工单自动分配给指定用户'),
    )

    auto_assign_to_group = forms.ModelChoiceField(
        required=False,
        queryset=Group.objects.all(),
        widget=forms.Select(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface appearance-none '
                     'focus:outline-none focus:ring-2 focus:ring-md-primary '
                     'transition cursor-pointer',
        }),
        label=_('自动分配给用户组'),
        help_text=_('该分类的工单自动分配给指定用户组'),
    )

    sla_hours = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface '
                     'placeholder-md-outline focus:outline-none '
                     'focus:ring-2 focus:ring-md-primary transition',
            'placeholder': '24',
        }),
        label=_('SLA时限(小时)'),
    )

    is_active = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 '
                     'text-md-primary focus:ring-md-primary focus:ring-2 '
                     'transition cursor-pointer accent-md-primary',
        }),
        label=_('是否启用'),
    )

    allow_banned_users = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 '
                     'text-md-primary focus:ring-md-primary focus:ring-2 '
                     'transition cursor-pointer accent-md-primary',
        }),
        label=_('允许封禁用户提交'),
        help_text=_('勾选后，被封禁的用户可以在此分类下提交工单'),
    )

    display_order = forms.IntegerField(
        initial=0,
        widget=forms.NumberInput(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface '
                     'placeholder-md-outline focus:outline-none '
                     'focus:ring-2 focus:ring-md-primary transition',
            'placeholder': '0',
        }),
        label=_('显示顺序'),
    )

    class Meta:
        model = TicketCategory
        fields = [
            'name', 'description', 'icon',
            'default_priority', 'auto_assign_to', 'auto_assign_to_group',
            'sla_hours',
            'is_active', 'allow_banned_users', 'display_order',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.fields['auto_assign_to'].queryset = User.objects.filter(
            is_staff=True
        ).order_by('username')


class AdminTicketCommentForm(forms.ModelForm):
    """
    工单评论表单（超管后台）

    超管可添加内部备注。
    """

    content = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 '
                     'rounded-md px-4 py-3 text-md-on-surface '
                     'placeholder-md-outline focus:outline-none '
                     'focus:ring-2 focus:ring-md-primary transition resize-y',
            'rows': 3,
            'placeholder': '请输入评论内容...',
        }),
        label=_('评论内容'),
    )

    is_internal = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 '
                     'text-md-primary focus:ring-md-primary focus:ring-2 '
                     'transition cursor-pointer accent-md-primary',
        }),
        label=_('内部备注'),
        help_text=_('仅工作人员可见'),
    )

    class Meta:
        model = TicketComment
        fields = ['content', 'is_internal']
