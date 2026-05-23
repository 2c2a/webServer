"""
主机管理 - 超管后台表单

超管可操作所有字段，无提供商数据隔离。
包含主机创建/编辑表单和主机组表单。
"""

import os

from django import forms
from django.contrib.auth import get_user_model
from django.conf import settings

from utils.provider import PROVIDER_GROUP_NAME
from .models import Host, HostGroup
from .forms_wizard import (
    validate_certificate_pem,
    validate_private_key_pem,
    _ensure_cert_dir,
)

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
MULTI_SELECT_CLASS = (
    'w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 '
    'rounded px-3 py-2 text-slate-200 '
    'focus:outline-none focus:ring-1 focus:ring-cyan-500/50 '
    'focus:border-cyan-500 transition min-h-[120px]'
)
FILE_INPUT_CLASS = (
    'w-full text-sm text-slate-200 file:mr-4 file:py-2 file:px-4 '
    'file:rounded file:border-0 file:text-sm file:font-medium '
    'file:bg-cyan-600/20 file:text-cyan-400 hover:file:bg-cyan-600/30 '
    'file:cursor-pointer cursor-pointer'
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
            'placeholder': '输入远程主机登录密码',
            'autocomplete': 'new-password',
        }),
        required=False,
        label='密码',
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
            'auth_method', 'port', 'rdp_port',
            'use_ssl', 'username',
            'providers',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机名称',
            }),
            'os_type': forms.Select(attrs={
                'class': SELECT_CLASS,
            }),
            'hostname': forms.TextInput(attrs={
                'class': INPUT_CLASS,
                'placeholder': '输入主机地址',
            }),
            'connection_type': forms.Select(attrs={
                'class': SELECT_CLASS,
            }),
            'auth_method': forms.Select(attrs={
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
            'os_type': '主机系统',
            'hostname': '主机地址',
            'connection_type': '连接类型',
            'auth_method': '连接方式',
            'port': 'WinRM端口',
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

        self.fields['os_type'].choices = Host.OS_TYPE_CHOICES
        self.fields['connection_type'].choices = [
            ('winrm', 'WinRM'),
            ('localwinserver', '本地WinServer'),
        ]
        self.fields['auth_method'].choices = Host.AUTH_METHOD_CHOICES

        if self.instance.pk:
            self.fields['password'].help_text = (
                '留空则不修改密码。为安全起见，此处不显示原密码。'
            )
            self.fields['password'].required = False

    def clean(self):
        cleaned_data = super().clean()
        connection_type = cleaned_data.get('connection_type')
        auth_method = cleaned_data.get('auth_method')

        if connection_type == 'winrm' and auth_method == 'certificate':
            cert_pem = self.files.get('cert_pem')
            cert_key = self.files.get('cert_key')
            has_existing = (
                self.instance.pk
                and self.instance.cert_pem_path
                and os.path.exists(self.instance.cert_pem_path)
            )
            if not cert_pem and not has_existing:
                self.add_error('cert_pem', '证书认证方式必须上传客户端证书')
            if not cert_key and not has_existing:
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
            if not self.instance.pk and not cleaned_data.get('password'):
                self.add_error('password', 'NTLM认证方式必须填写密码')

        if connection_type == 'localwinserver':
            if not cleaned_data.get('username'):
                self.add_error('username', '必须填写用户名')
            if not self.instance.pk and not cleaned_data.get('password'):
                self.add_error('password', '必须填写密码')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        auth_method = self.cleaned_data.get('auth_method')
        connection_type = self.cleaned_data.get('connection_type')
        password = self.cleaned_data.get('password')

        if self.instance.pk:
            if password:
                instance.password = password
        else:
            if connection_type == 'winrm' and auth_method == 'ntlm':
                instance.password = password
            elif connection_type == 'winrm' and auth_method == 'certificate':
                instance.cert_pem_path = instance.cert_pem_path or ''
                instance.cert_key_path = instance.cert_key_path or ''
            elif connection_type == 'localwinserver':
                instance.password = password

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

        self.fields['hosts'].queryset = Host.objects.order_by('name')

        provider_users = User.objects.filter(
            groups__name=PROVIDER_GROUP_NAME,
            is_staff=True,
            is_superuser=False,
        ).order_by('username')
        self.fields['providers'].queryset = provider_users
