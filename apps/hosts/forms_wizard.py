"""
主机管理 - 向导式创建表单

分步引导超管添加主机，提供智能默认值和逐步验证。
与 AdminHostForm 不同，此表单专注于创建流程的简化和引导。
"""

import os

from django import forms
from django.contrib.auth import get_user_model
from django.conf import settings

from utils.provider import PROVIDER_GROUP_NAME
from .models import Host

User = get_user_model()

INPUT_CLASS = (
    'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 '
    'rounded px-3 py-2 text-slate-200 placeholder-slate-500 '
    'focus:outline-none focus:ring-1 focus:ring-cyan-500/50 '
    'focus:border-cyan-500 transition'
)
SELECT_CLASS = (
    'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 '
    'rounded px-3 py-2 text-slate-200 appearance-none '
    'focus:outline-none focus:ring-1 focus:ring-cyan-500/50 '
    'focus:border-cyan-500 transition cursor-pointer'
)
CHECKBOX_CLASS = (
    'w-5 h-5 rounded border-slate-700/50 bg-slate-900/50 '
    'text-cyan-400 focus:ring-cyan-500 focus:ring-2 transition '
    'accent-cyan-500 cursor-pointer'
)
FILE_INPUT_CLASS = (
    'w-full text-sm text-slate-200 file:mr-4 file:py-2 file:px-4 '
    'file:rounded file:border-0 file:text-sm file:font-medium '
    'file:bg-cyan-600/20 file:text-cyan-400 hover:file:bg-cyan-600/30 '
    'file:cursor-pointer cursor-pointer'
)

CONNECTION_DEFAULT_PORTS = {
    'winrm': 5985,
    'localwinserver': 5985,
    'ssh': 22,
    'tunnel': 5985,
}

CONNECTION_DEFAULT_SSL = {
    'winrm': False,
    'localwinserver': False,
    'ssh': False,
    'tunnel': False,
}

CERT_STORAGE_DIR = os.path.join(settings.MEDIA_ROOT, 'certs', 'hosts')


def _ensure_cert_dir(host_pk):
    d = os.path.join(CERT_STORAGE_DIR, str(host_pk))
    os.makedirs(d, exist_ok=True)
    return d


def validate_certificate_pem(content: bytes, field_name: str = '证书') -> None:
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        raise forms.ValidationError(f'{field_name}文件编码无效，必须为UTF-8文本格式')
    if '-----BEGIN' not in text:
        raise forms.ValidationError(f'{field_name}文件格式无效，不是合法的PEM格式')
    if '-----END' not in text:
        raise forms.ValidationError(f'{field_name}文件格式无效，不是合法的PEM格式')


def validate_private_key_pem(content: bytes) -> None:
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        raise forms.ValidationError('私钥文件编码无效，必须为UTF-8文本格式')
    if '-----BEGIN' not in text:
        raise forms.ValidationError('私钥文件格式无效，不是合法的PEM格式')
    if 'PRIVATE KEY' not in text:
        raise forms.ValidationError('私钥文件格式无效，未包含私钥标识')
    if '-----END' not in text:
        raise forms.ValidationError('私钥文件格式无效，不是合法的PEM格式')
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.hazmat.backends import default_backend
        load_pem_private_key(content, password=None, backend=default_backend())
    except ImportError:
        pass
    except Exception as e:
        raise forms.ValidationError(f'私钥文件无效: {str(e)}')


class HostWizardForm(forms.ModelForm):
    """
    主机创建向导表单

    分为三步：
    - Step 1: 基本信息 (name, os_type, hostname, connection_type)
    - Step 2: 连接配置 (port, auth_method, username/password 或 证书)
    - Step 3: 分配提供商 (providers, description)
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': INPUT_CLASS,
            'placeholder': '输入远程主机登录密码',
            'autocomplete': 'new-password',
            'x-model': 'password',
        }),
        required=False,
        label='密码',
    )

    tunnel_token = forms.CharField(
        widget=forms.HiddenInput(attrs={
            'x-model': 'tunnelToken',
        }),
        required=False,
    )

    cert_config_method = forms.CharField(
        widget=forms.HiddenInput(attrs={
            'x-model': 'certConfigMethod',
        }),
        required=False,
        initial='quick',
    )

    cert_pem = forms.FileField(
        label='客户端证书(公钥)',
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_INPUT_CLASS,
            'accept': '.pem,.cer,.crt,.cert',
        }),
        help_text='PEM格式的客户端证书文件',
    )

    cert_key = forms.FileField(
        label='客户端私钥',
        required=False,
        widget=forms.ClearableFileInput(attrs={
            'class': FILE_INPUT_CLASS,
            'accept': '.pem,.key',
        }),
        help_text='PEM格式的客户端私钥文件',
    )

    class Meta:
        model = Host
        fields = [
            'name', 'os_type', 'hostname', 'connection_type',
            'auth_method', 'port', 'rdp_port', 'use_ssl',
            'username', 'password',
            'providers', 'description',
            'tunnel_token',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机名称，如: 北京服务器-01',
                'x-model': 'name',
            }),
            'os_type': forms.Select(attrs={
                'class': SELECT_CLASS,
                'x-model': 'osType',
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
            'auth_method': forms.Select(attrs={
                'class': SELECT_CLASS,
                'x-model': 'authMethod',
                'x-on:change': 'onAuthMethodChange()',
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
            'os_type': '主机系统',
            'hostname': '主机地址',
            'connection_type': '连接类型',
            'auth_method': '连接方式',
            'port': 'WinRM端口',
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

        self.fields['os_type'].choices = Host.OS_TYPE_CHOICES

        self.fields['connection_type'].choices = [
            ('winrm', 'WinRM'),
            ('localwinserver', '本地WinServer'),
        ]

        self.fields['auth_method'].choices = Host.AUTH_METHOD_CHOICES

    def clean(self):
        cleaned_data = super().clean()
        connection_type = cleaned_data.get('connection_type')
        hostname = cleaned_data.get('hostname')
        auth_method = cleaned_data.get('auth_method')

        if connection_type == 'tunnel' and not hostname:
            cleaned_data['hostname'] = 'tunnel-pending'

        tunnel_token = cleaned_data.get('tunnel_token')
        if tunnel_token == '':
            cleaned_data['tunnel_token'] = None

        if connection_type == 'winrm' and auth_method == 'certificate':
            cert_config_method = cleaned_data.get('cert_config_method', 'quick')
            cert_pem = self.files.get('cert_pem')
            cert_key = self.files.get('cert_key')
            if cert_config_method == 'manual':
                if not cert_pem:
                    self.add_error('cert_pem', '证书认证方式必须上传客户端证书')
                if not cert_key:
                    self.add_error('cert_key', '证书认证方式必须上传客户端私钥')
            if cert_pem:
                try:
                    validate_certificate_pem(cert_pem.read())
                except forms.ValidationError as e:
                    self.add_error('cert_pem', e)
                finally:
                    cert_pem.seek(0)
            if cert_key:
                try:
                    validate_private_key_pem(cert_key.read())
                except forms.ValidationError as e:
                    self.add_error('cert_key', e)
                finally:
                    cert_key.seek(0)

        if connection_type == 'winrm' and auth_method == 'ntlm':
            if not cleaned_data.get('username'):
                self.add_error('username', 'NTLM认证方式必须填写用户名')
            if not cleaned_data.get('password'):
                self.add_error('password', 'NTLM认证方式必须填写密码')

        if connection_type == 'localwinserver':
            if not cleaned_data.get('username'):
                self.add_error('username', '必须填写用户名')
            if not cleaned_data.get('password'):
                self.add_error('password', '必须填写密码')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        auth_method = self.cleaned_data.get('auth_method')
        connection_type = self.cleaned_data.get('connection_type')

        if connection_type == 'winrm' and auth_method == 'ntlm':
            instance.password = self.cleaned_data.get('password')
        elif connection_type == 'winrm' and auth_method == 'certificate':
            instance.cert_pem_path = ''
            instance.cert_key_path = ''
        elif connection_type == 'localwinserver':
            instance.password = self.cleaned_data.get('password')

        if commit:
            instance.save()
            self.save_m2m()
            if connection_type == 'winrm' and auth_method == 'certificate':
                self._save_cert_files(instance)

        return instance

    def _save_cert_files(self, host):
        cert_pem = self.files.get('cert_pem')
        cert_key = self.files.get('cert_key')
        if not cert_pem or not cert_key:
            return

        cert_dir = _ensure_cert_dir(host.pk)
        pem_path = os.path.join(cert_dir, 'client.pem')
        key_path = os.path.join(cert_dir, 'client.key')

        with open(pem_path, 'wb') as f:
            for chunk in cert_pem.chunks():
                f.write(chunk)

        with open(key_path, 'wb') as f:
            for chunk in cert_key.chunks():
                f.write(chunk)

        os.chmod(pem_path, 0o600)
        os.chmod(key_path, 0o600)

        host.cert_pem_path = pem_path
        host.cert_key_path = key_path
        Host.objects.filter(pk=host.pk).update(
            cert_pem_path=pem_path,
            cert_key_path=key_path,
        )

    def get_providers_with_host_count(self):
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
