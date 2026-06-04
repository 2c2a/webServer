"""
运营管理 - 超级管理员后台表单

包含产品、产品组、开户申请驳回等表单。
超管可查看所有记录；站点组管理员仅可查看当前站点组记录；
提供商仅可查看自己相关的记录。
"""

import json
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Product, ProductGroup


# MD3 风格的通用 CSS 类
_INPUT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md '
    'px-4 py-3 text-md-on-surface placeholder-md-outline '
    'focus:outline-none focus:ring-2 focus:ring-md-primary transition'
)
_SELECT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md '
    'px-4 py-3 text-md-on-surface appearance-none '
    'focus:outline-none focus:ring-2 focus:ring-md-primary '
    'transition cursor-pointer'
)
_CHECKBOX_CLASS = (
    'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 '
    'text-md-primary focus:ring-md-primary focus:ring-2 '
    'transition cursor-pointer accent-md-primary'
)
_TEXTAREA_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md '
    'px-4 py-3 text-md-on-surface placeholder-md-outline '
    'focus:outline-none focus:ring-2 focus:ring-md-primary '
    'transition resize-y'
)


class AdminProductForm(forms.ModelForm):
    """
    超管产品管理表单

    与提供商表单类似，但不做数据隔离：
    - 所有主机均可选择
    - 所有产品组均可选择
    """

    default_disk_quota = forms.CharField(
        label=_('默认磁盘配额'),
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': '{"C:": 10240, "D:": 20480}',
            'class': _TEXTAREA_CLASS + ' font-mono text-sm',
        }),
        help_text=_(
            '每个磁盘的默认配额大小（MB），'
            'JSON 格式，如 {"C:": 10240, "D:": 20480}'
        ),
    )

    allow_extra_quota_disks = forms.CharField(
        label=_('允许额外申请容量的磁盘'),
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 2,
            'placeholder': '["C:", "D:"]',
            'class': _TEXTAREA_CLASS + ' font-mono text-sm',
        }),
        help_text=_(
            '允许用户在申请时额外申请容量的磁盘列表，'
            'JSON 数组格式，如 ["C:", "D:"]'
        ),
    )

    class Meta:
        model = Product
        fields = [
            'display_name', 'display_description',
            'product_group',
            'host', 'is_available', 'auto_approval', 'visibility',
            'enable_host_protection',
            'display_hostname', 'rdp_port',
            'enable_disk_quota',
        ]
        widgets = {
            'display_name': forms.TextInput(attrs={
                'class': _INPUT_CLASS,
                'placeholder': '输入产品显示名称',
            }),
            'display_description': forms.Textarea(attrs={
                'class': _TEXTAREA_CLASS,
                'rows': 3,
                'placeholder': '输入产品显示描述（可选）',
            }),
            'product_group': forms.Select(attrs={
                'class': _SELECT_CLASS,
            }),
            'host': forms.Select(attrs={
                'class': _SELECT_CLASS,
            }),
            'is_available': forms.CheckboxInput(attrs={
                'class': _CHECKBOX_CLASS,
            }),
            'auto_approval': forms.CheckboxInput(attrs={
                'class': _CHECKBOX_CLASS,
            }),
            'visibility': forms.Select(attrs={
                'class': _SELECT_CLASS,
            }),
            'enable_host_protection': forms.CheckboxInput(attrs={
                'class': _CHECKBOX_CLASS,
            }),
            'display_hostname': forms.TextInput(attrs={
                'class': _INPUT_CLASS,
                'placeholder': '输入显示地址',
            }),
            'rdp_port': forms.NumberInput(attrs={
                'class': _INPUT_CLASS,
                'placeholder': '3389',
            }),
            'enable_disk_quota': forms.CheckboxInput(attrs={
                'class': _CHECKBOX_CLASS,
            }),
        }
        labels = {
            'display_name': _('显示名称'),
            'display_description': _('显示描述'),
            'product_group': _('产品组'),
            'host': _('关联主机'),
            'is_available': _('是否可用'),
            'auto_approval': _('自动审核'),
            'visibility': _('可见性'),
            'enable_host_protection': _('启用主机保护(Gateway)'),
            'display_hostname': _('显示地址'),
            'rdp_port': _('RDP端口'),
            'enable_disk_quota': _('启用磁盘配额管理'),
        }
        help_texts = {
            'host': _('此产品运行所在的主机'),
            'is_available': _('是否在前端展示此产品'),
            'auto_approval': _('是否自动批准针对此产品的开户申请'),
            'visibility': _(
                '公开对所有用户可见，'
                '邀请访问仅对已授权用户可见'
            ),
            'enable_host_protection': _(
                '启用后，用户只能通过Gateway隧道访问RDP，'
                '主机不暴露公网IP。需部署Gateway服务。'
            ),
            'enable_disk_quota': _(
                '是否启用磁盘配额管理，'
                '启用后将自动为新用户设置磁盘配额'
            ),
        }

    def __init__(self, *args, user=None, site_group=None, **kwargs):
        super().__init__(*args, **kwargs)

        from apps.hosts.models import Host
        from utils.provider import get_provider_hosts

        if user and user.is_superuser:
            host_qs = Host.objects.all()
            pg_qs = ProductGroup.objects.all()
        elif user and site_group and user.is_site_group_admin(site_group):
            host_qs = Host.objects.filter(site_group=site_group)
            pg_qs = ProductGroup.objects.filter(site_group=site_group)
        elif user:
            host_qs = get_provider_hosts(user, site_group=site_group)
            pg_qs = ProductGroup.objects.filter(created_by=user)
        else:
            host_qs = Host.objects.all()
            pg_qs = ProductGroup.objects.all()

        self.fields['host'].queryset = host_qs.order_by('name')
        self.fields['product_group'].queryset = pg_qs.order_by('name')

        # 初始化 JSON 字段的显示值
        if self.instance and self.instance.pk:
            if self.instance.default_disk_quota:
                self.initial['default_disk_quota'] = json.dumps(
                    self.instance.default_disk_quota,
                    ensure_ascii=False,
                    indent=2,
                )
            if self.instance.allow_extra_quota_disks:
                self.initial['allow_extra_quota_disks'] = json.dumps(
                    self.instance.allow_extra_quota_disks,
                    ensure_ascii=False,
                )

    def clean_default_disk_quota(self):
        data = self.cleaned_data.get('default_disk_quota', '')
        if not data or not data.strip():
            return {}
        if isinstance(data, dict):
            return data
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError('磁盘配额格式无效，请输入有效的 JSON')
        if not isinstance(parsed, dict):
            raise forms.ValidationError(
                '磁盘配额必须为字典格式，如 {"C:": 10240}'
            )
        for disk, value in parsed.items():
            try:
                val = int(value)
                if val < 0:
                    raise forms.ValidationError(
                        f'磁盘 {disk} 的配额不能为负数'
                    )
            except (ValueError, TypeError):
                raise forms.ValidationError(
                    f'磁盘 {disk} 的配额必须为数字'
                )
        return parsed

    def clean_allow_extra_quota_disks(self):
        data = self.cleaned_data.get('allow_extra_quota_disks', '')
        if not data or not data.strip():
            return []
        if isinstance(data, list):
            return data
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError(
                '磁盘列表格式无效，请输入有效的 JSON 数组'
            )
        if not isinstance(parsed, list):
            raise forms.ValidationError(
                '磁盘列表必须为数组格式，如 ["C:", "D:"]'
            )
        return parsed

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.default_disk_quota = self.cleaned_data.get(
            'default_disk_quota', {}
        )
        instance.allow_extra_quota_disks = self.cleaned_data.get(
            'allow_extra_quota_disks', []
        )
        if commit:
            instance.save()
        return instance


class AdminProductGroupForm(forms.ModelForm):
    """
    超管产品组管理表单

    包含所有字段，不做数据隔离。
    """

    class Meta:
        model = ProductGroup
        fields = [
            'name', 'description',
            'display_order', 'is_active', 'visibility',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': _INPUT_CLASS,
                'placeholder': '输入产品组名称',
            }),
            'description': forms.Textarea(attrs={
                'class': _TEXTAREA_CLASS,
                'rows': 3,
                'placeholder': '输入产品组描述（可选）',
            }),
            'display_order': forms.NumberInput(attrs={
                'class': _INPUT_CLASS,
                'placeholder': '0',
                'min': '0',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': _CHECKBOX_CLASS,
            }),
            'visibility': forms.Select(attrs={
                'class': _SELECT_CLASS,
            }),
        }
        labels = {
            'name': _('产品组名称'),
            'description': _('描述'),
            'display_order': _('显示顺序'),
            'is_active': _('是否启用'),
            'visibility': _('可见性'),
        }
        help_texts = {
            'display_order': _(
                '产品组在前端展示的顺序，数字越小越靠前'
            ),
            'is_active': _('是否在前端展示此产品组'),
            'visibility': _(
                '公开对所有用户可见，'
                '邀请访问仅对已授权用户可见'
            ),
        }


class AdminRequestRejectForm(forms.Form):
    """
    超管驳回开户申请表单

    用于输入驳回原因
    """

    rejection_reason = forms.CharField(
        label='驳回原因',
        required=True,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'placeholder': '请输入驳回原因...',
            'class': _TEXTAREA_CLASS,
        }),
        help_text='驳回原因将作为审核备注发送给申请人',
    )
