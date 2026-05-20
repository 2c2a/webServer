"""
主机管理 - 超管后台表单

超管可操作所有字段，无提供商数据隔离。
包含主机创建/编辑表单和主机组表单。
"""

from django import forms
from django.contrib.auth import get_user_model

from utils.provider import PROVIDER_GROUP_NAME
from .models import Host, HostGroup

User = get_user_model()


# MD3 输入框样式常量
INPUT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md '
    'px-4 py-3 text-md-on-surface placeholder-md-outline '
    'focus:outline-none focus:ring-2 focus:ring-md-primary transition'
)
SELECT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md '
    'px-4 py-3 text-md-on-surface appearance-none '
    'focus:outline-none focus:ring-2 focus:ring-md-primary transition cursor-pointer'
)
CHECKBOX_CLASS = (
    'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 '
    'text-md-primary focus:ring-md-primary focus:ring-2 transition accent-md-primary'
)
MULTI_SELECT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md '
    'px-4 py-3 text-md-on-surface '
    'focus:outline-none focus:ring-2 focus:ring-md-primary transition min-h-[120px]'
)


class AdminHostForm(forms.ModelForm):
    """
    超管主机表单

    包含所有主机字段，无提供商过滤。
    密码字段可选，留空则自动生成（创建时）或不修改（编辑时）。
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
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
            'use_ssl', 'username',
            'providers',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机名称',
            }),
            'hostname': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机地址',
            }),
            'connection_type': forms.Select(attrs={
                'class': SELECT_CLASS,
            }),
            'port': forms.NumberInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '5985',
            }),
            'rdp_port': forms.NumberInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '3389',
            }),
            'username': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入连接用户名',
            }),
            'use_ssl': forms.CheckboxInput(attrs={
                'class': CHECKBOX_CLASS,
            }),
            'providers': forms.SelectMultiple(attrs={
                'class': MULTI_SELECT_CLASS,
                'size': '6',
            }),
        }
        labels = {
            'name': '主机名称',
            'hostname': '主机地址',
            'connection_type': '连接类型',
            'port': '连接端口',
            'rdp_port': 'RDP端口',
            'use_ssl': '使用SSL',
            'username': '用户名',
            'providers': '管理提供商',
        }
        help_texts = {
            'providers': '按住 Ctrl / Cmd 可多选提供商',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        provider_users = User.objects.filter(
            groups__name=PROVIDER_GROUP_NAME,
            is_staff=True,
            is_superuser=False,
        ).order_by('username')
        self.fields['providers'].queryset = provider_users

        if self.instance.pk:
            self.fields['password'].help_text = (
                '留空则不修改密码。为安全起见，此处不显示原密码。'
            )
            self.fields['password'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get('password')

        if self.instance.pk:
            # 编辑模式：仅当密码不为空时修改
            if password:
                instance.password = password
        else:
            # 创建模式：密码为空则自动生成
            if password:
                instance.password = password
            else:
                from .forms_provider import generate_random_password
                self.generated_password = generate_random_password()
                instance.password = self.generated_password

        if commit:
            instance.save()
            self.save_m2m()
        return instance


class AdminHostGroupForm(forms.ModelForm):
    """
    超管主机组表单

    包含所有主机组字段，无提供商过滤。
    providers 字段显示所有提供商组用户。
    """

    class Meta:
        model = HostGroup
        fields = ['name', 'description', 'hosts', 'providers']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机组名称',
            }),
            'description': forms.Textarea(attrs={
                'class': INPUT_CLASS + ' resize-y',
                'rows': 3,
                'placeholder': '输入主机组描述（可选）',
            }),
            'hosts': forms.SelectMultiple(attrs={
                'class': MULTI_SELECT_CLASS,
                'size': '8',
            }),
            'providers': forms.SelectMultiple(attrs={
                'class': MULTI_SELECT_CLASS,
                'size': '6',
            }),
        }
        labels = {
            'name': '组名称',
            'description': '描述',
            'hosts': '主机',
            'providers': '管理提供商',
        }
        help_texts = {
            'hosts': '按住 Ctrl / Cmd 可选主机',
            'providers': '按住 Ctrl / Cmd 可多选提供商',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # hosts: 所有主机
        self.fields['hosts'].queryset = Host.objects.order_by('name')

        # providers: 所有提供商组用户
        provider_users = User.objects.filter(
            groups__name=PROVIDER_GROUP_NAME,
            is_staff=True,
            is_superuser=False,
        ).order_by('username')
        self.fields['providers'].queryset = provider_users
