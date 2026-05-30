"""
主机管理 - 提供商后台表单

包含主机创建和编辑表单，复用 Admin 中的密码处理逻辑。
"""

import secrets
import string

from django import forms

from .models import Host, HostGroup


def generate_random_password(length=16):
    """
    生成随机复杂密码

    包含大写字母、小写字母、数字和特殊字符，确保密码强度。
    """
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*()_+-=[]{}|;:,.<>?'
    while True:
        password = ''.join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
        if has_upper and has_lower and has_digit and has_special:
            return password


class HostCreateForm(forms.ModelForm):
    """
    主机创建表单

    密码字段为必填，可自动生成随机密码。
    创建时自动设置 created_by 为当前用户。
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
            'placeholder': '输入密码或留空自动生成',
            'autocomplete': 'new-password',
        }),
        required=False,
        help_text='留空将自动生成随机密码',
        label='密码',
    )

    class Meta:
        model = Host
        fields = [
            'name', 'hostname', 'connection_type', 'port', 'rdp_port',
            'use_ssl', 'username', 'os_version', 'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '输入主机名称',
            }),
            'hostname': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '输入主机地址',
            }),
            'connection_type': forms.Select(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface appearance-none focus:outline-none focus:ring-2 focus:ring-md-primary transition cursor-pointer',
            }),
            'port': forms.NumberInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '5985',
            }),
            'rdp_port': forms.NumberInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '3389',
            }),
            'username': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '输入连接用户名',
            }),
            'os_version': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '例如: Windows Server 2022',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition resize-y',
                'rows': 3,
                'placeholder': '输入主机描述（可选）',
            }),
            'use_ssl': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 text-md-primary focus:ring-md-primary focus:ring-2 transition',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.generated_password = None
        super().__init__(*args, **kwargs)
        # 创建时密码可选（自动生成）
        self.fields['password'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            instance.password = password
        else:
            # 自动生成随机密码
            self.generated_password = generate_random_password()
            instance.password = self.generated_password
        if commit:
            instance.save()
        return instance


class HostUpdateForm(forms.ModelForm):
    """
    主机编辑表单

    密码字段可选，留空则不修改。
    不允许修改 created_by 和 providers 字段。
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
            'placeholder': '留空则不修改密码',
            'autocomplete': 'new-password',
        }),
        required=False,
        help_text='留空则不修改密码。为安全起见，此处不显示原密码。',
        label='密码',
    )

    class Meta:
        model = Host
        fields = [
            'name', 'hostname', 'connection_type', 'port', 'rdp_port',
            'use_ssl', 'username', 'os_version', 'status', 'description',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '输入主机名称',
            }),
            'hostname': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '输入主机地址',
            }),
            'connection_type': forms.Select(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface appearance-none focus:outline-none focus:ring-2 focus:ring-md-primary transition cursor-pointer',
            }),
            'port': forms.NumberInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '5985',
            }),
            'rdp_port': forms.NumberInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '3389',
            }),
            'username': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '输入连接用户名',
            }),
            'os_version': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '例如: Windows Server 2022',
            }),
            'status': forms.Select(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface appearance-none focus:outline-none focus:ring-2 focus:ring-md-primary transition cursor-pointer',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition resize-y',
                'rows': 3,
                'placeholder': '输入主机描述（可选）',
            }),
            'use_ssl': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 text-md-primary focus:ring-md-primary focus:ring-2 transition',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['password'].help_text = '留空则不修改密码。为安全起见，此处不显示原密码。'

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('password'):
            instance.password = self.cleaned_data['password']
        if commit:
            instance.save()
        return instance


class HostGroupForm(forms.ModelForm):
    """
    主机组表单

    提供商只能选择自己可见的主机和提供商。
    hosts 和 providers 字段按当前提供商过滤。
    """

    class Meta:
        model = HostGroup
        fields = ['name', 'description', 'hosts', 'providers']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition',
                'placeholder': '输入主机组名称',
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition resize-y',
                'rows': 3,
                'placeholder': '输入主机组描述（可选）',
            }),
            'hosts': forms.SelectMultiple(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface focus:outline-none focus:ring-2 focus:ring-md-primary transition min-h-[120px]',
                'size': '8',
            }),
            'providers': forms.SelectMultiple(attrs={
                'class': 'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface focus:outline-none focus:ring-2 focus:ring-md-primary transition min-h-[80px]',
                'size': '5',
            }),
        }
        labels = {
            'name': '组名称',
            'description': '描述',
            'hosts': '主机',
            'providers': '管理提供商',
        }
        help_texts = {
            'hosts': '按住 Ctrl / Cmd 可多选主机',
            'providers': '按住 Ctrl / Cmd 可多选提供商',
        }

    def __init__(self, *args, **kwargs):
        self.provider_user = kwargs.pop('provider_user', None)
        super().__init__(*args, **kwargs)

        if self.provider_user:
            # 过滤 hosts：只显示当前提供商可见的主机
            from utils.provider import get_provider_hosts
            self.fields['hosts'].queryset = get_provider_hosts(
                self.provider_user
            ).order_by('name')

            # 过滤 providers：只显示提供商组的用户
            from django.contrib.auth.models import User
            from utils.provider import is_provider, PROVIDER_GROUP_NAME
            provider_users = User.objects.filter(
                groups__name=PROVIDER_GROUP_NAME,
                is_staff=True,
                is_superuser=False,
            ).order_by('username')
            self.fields['providers'].queryset = provider_users
