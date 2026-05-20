"""
主机管理 - 向导式创建表单

分步引导超管添加主机，提供智能默认值和逐步验证。
与 AdminHostForm 不同，此表单专注于创建流程的简化和引导。
"""

from django import forms
from django.contrib.auth import get_user_model

from utils.provider import PROVIDER_GROUP_NAME
from .models import Host

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

# 连接类型 -> 默认端口映射
CONNECTION_DEFAULT_PORTS = {
    'winrm': 5985,
    'ssh': 22,
    'localwinserver': 5985,
    'tunnel': 5985,
}

# 连接类型 -> 默认SSL映射
CONNECTION_DEFAULT_SSL = {
    'winrm': False,
    'ssh': False,
    'localwinserver': False,
    'tunnel': False,
}


class HostWizardForm(forms.ModelForm):
    """
    主机创建向导表单

    分为三步：
    - Step 1: 基本信息 (name, hostname, connection_type)
    - Step 2: 连接配置 (port, rdp_port, use_ssl, username, password) 或 执行命令 (隧道模式)
    - Step 3: 分配提供商 (providers, description)

    智能默认值：
    - port 根据连接类型自动设置 (winrm=5985, ssh=22)
    - use_ssl 根据端口自动判断 (5986=True)
    - 密码留空时自动生成
    - 隧道模式下hostname非必填，自动生成
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '输入密码或留空自动生成',
            'autocomplete': 'new-password',
            'x-model': 'password',
        }),
        required=False,
        help_text='留空将自动生成随机密码',
        label='密码',
    )

    tunnel_token = forms.CharField(
        widget=forms.HiddenInput(attrs={
            'x-model': 'tunnelToken',
        }),
        required=False,
    )

    class Meta:
        model = Host
        fields = [
            'name', 'hostname', 'connection_type',
            'port', 'rdp_port', 'use_ssl', 'username', 'password',
            'providers', 'description',
            'tunnel_token',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机名称，如: 北京服务器-01',
                'x-model': 'name',
            }),
            'hostname': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机地址，如: 192.168.1.100',
                'x-model': 'hostname',
            }),
            'connection_type': forms.Select(attrs={
                'class': SELECT_CLASS,
                'x-model': 'connectionType',
                'x-on:change': 'onConnectionTypeChange()',
            }),
            'port': forms.NumberInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '5985',
                'x-model': 'port',
            }),
            'rdp_port': forms.NumberInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '3389',
                'x-model.number': 'rdpPort',
            }),
            'use_ssl': forms.CheckboxInput(attrs={
                'class': CHECKBOX_CLASS,
                'x-model': 'useSsl',
            }),
            'username': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入连接用户名，如: Administrator',
                'x-model': 'username',
            }),
            'description': forms.Textarea(attrs={
                'class': INPUT_CLASS + ' resize-y',
                'rows': 3,
                'placeholder': '输入主机描述（可选）',
                'x-model': 'description',
            }),
            'providers': forms.CheckboxSelectMultiple(),
        }
        labels = {
            'name': '主机名称',
            'hostname': '主机地址',
            'connection_type': '连接类型',
            'port': '连接端口',
            'rdp_port': 'RDP端口',
            'use_ssl': '使用SSL',
            'username': '用户名',
            'description': '描述',
            'providers': '管理提供商',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        provider_users = User.objects.filter(
            groups__name=PROVIDER_GROUP_NAME,
            is_staff=True,
            is_superuser=False,
        ).order_by('username')
        self.fields['providers'].queryset = provider_users

        if not self.initial.get('port'):
            self.initial['port'] = 5985
        if not self.initial.get('rdp_port'):
            self.initial['rdp_port'] = 3389

    def clean(self):
        cleaned_data = super().clean()
        connection_type = cleaned_data.get('connection_type')
        hostname = cleaned_data.get('hostname')

        if connection_type == 'tunnel' and not hostname:
            cleaned_data['hostname'] = 'tunnel-pending'

        tunnel_token = cleaned_data.get('tunnel_token')
        if tunnel_token == '':
            cleaned_data['tunnel_token'] = None

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get('password')

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

    def get_providers_with_host_count(self):
        """
        返回提供商列表及其当前管理的主机数量，
        用于向导第三步的上下文展示。
        """
        providers = self.fields['providers'].queryset
        result = []
        for provider in providers:
            host_count = provider.provider_hosts.count()
            result.append({
                'id': provider.pk,
                'username': provider.username,
                'host_count': host_count,
            })
        return result
