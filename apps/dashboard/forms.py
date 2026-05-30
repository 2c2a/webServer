"""
仪表盘表单
"""
from django import forms
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from .models import DashboardWidget, SystemConfig

MD_INPUT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 '
    'text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 '
    'focus:ring-md-primary transition'
)
MD_SELECT_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 '
    'text-md-on-surface appearance-none focus:outline-none focus:ring-2 '
    'focus:ring-md-primary transition cursor-pointer'
)
MD_CHECKBOX_CLASS = (
    'w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 text-md-primary '
    'focus:ring-md-primary focus:ring-2 transition cursor-pointer accent-md-primary'
)
MD_TEXTAREA_CLASS = (
    'w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 '
    'text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 '
    'focus:ring-md-primary transition resize-y'
)


class DashboardWidgetForm(forms.ModelForm):
    """
    仪表盘组件表单
    用于创建和编辑仪表盘组件
    """
    class Meta:
        model = DashboardWidget
        fields = [
            'widget_type', 'title', 'display_order',
            'is_enabled', 'widget_config'
        ]
        widgets = {
            'widget_type': forms.Select(attrs={
                'class': MD_SELECT_CLASS
            }),
            'title': forms.TextInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '请输入组件标题'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': MD_INPUT_CLASS,
                'min': 0
            }),
            'is_enabled': forms.CheckboxInput(attrs={
                'class': MD_CHECKBOX_CLASS
            }),
            'widget_config': forms.Textarea(attrs={
                'class': MD_TEXTAREA_CLASS,
                'rows': 5,
                'placeholder': '请输入JSON格式的配置参数'
            })
        }

    def clean_widget_config(self):
        """
        验证widget_config字段
        确保是有效的JSON格式
        """
        import json
        config = self.cleaned_data.get('widget_config')

        if config:
            try:
                json.loads(config)
            except json.JSONDecodeError:
                raise forms.ValidationError('配置参数必须是有效的JSON格式')

        return config


class WidgetConfigForm(forms.Form):
    """
    组件配置表单
    用于快速配置仪表盘组件
    """
    widget_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True
    )
    is_enabled = forms.BooleanField(
        label='启用组件',
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': MD_CHECKBOX_CLASS
        })
    )
    display_order = forms.IntegerField(
        label='显示顺序',
        required=True,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': MD_INPUT_CLASS
        })
    )


class SystemConfigForm(forms.ModelForm):
    """系统配置表单"""

    _PRESERVE_IF_EMPTY = [
        'smtp_password',
    ]

    class Meta:
        model = SystemConfig
        fields = [
            'site_name',
            'icp_number',
            'police_number',
            'smtp_host',
            'smtp_port',
            'smtp_use_tls',
            'smtp_username',
            'smtp_password',
            'smtp_from_email',
            'captcha_provider',
            'captcha_type',
            'login_captcha_type',
            'register_captcha_type',
            'email_captcha_type',
            'email_suffix_whitelist',
            'email_suffix_blacklist',
        ]
        widgets = {
            'site_name': forms.TextInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '请输入站点名称'
            }),
            'icp_number': forms.TextInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '例如：京ICP备12345678号'
            }),
            'police_number': forms.TextInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '例如：京公网安备 11010502000000号'
            }),
            'enable_registration': forms.CheckboxInput(attrs={
                'class': MD_CHECKBOX_CLASS
            }),
            'smtp_host': forms.TextInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '请输入SMTP服务器地址'
            }),
            'smtp_port': forms.NumberInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '请输入SMTP端口'
            }),
            'smtp_use_tls': forms.CheckboxInput(attrs={
                'class': MD_CHECKBOX_CLASS
            }),
            'smtp_username': forms.EmailInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '请输入SMTP用户名'
            }),
            'smtp_password': forms.PasswordInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '请输入SMTP密码',
                'render_value': True
            }),
            'smtp_from_email': forms.EmailInput(attrs={
                'class': MD_INPUT_CLASS,
                'placeholder': '请输入发件人邮箱'
            }),
            'captcha_provider': forms.Select(attrs={
                'class': MD_SELECT_CLASS
            }),
            'email_suffix_whitelist': forms.Textarea(attrs={
                'class': MD_TEXTAREA_CLASS,
                'rows': 5,
                'placeholder': (
                    '每行一个允许的邮箱后缀，例如：\n'
                    '@example.com\n@gmail.com\n@company.com'
                )
            }),
            'email_suffix_blacklist': forms.Textarea(attrs={
                'class': MD_TEXTAREA_CLASS,
                'rows': 5,
                'placeholder': (
                    '每行一个禁止的邮箱后缀，例如：\n'
                    '@tempmail.com\n@spam.com'
                )
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_values = {}
        if self.instance and self.instance.pk:
            for field in self._PRESERVE_IF_EMPTY:
                self._original_values[field] = getattr(
                    self.instance, field
                )
            for field in self._PRESERVE_IF_EMPTY:
                self.fields[field].required = False

    def clean_smtp_port(self):
        """验证SMTP端口"""
        port = self.cleaned_data.get('smtp_port')
        if port and (port < 1 or port > 65535):
            raise forms.ValidationError('端口号必须在1-65535之间')
        return port

    def clean(self):
        cleaned = super().clean()
        if cleaned is None:
            cleaned = {}
        return cleaned

    def save(self, commit=True):
        config = super().save(commit=False)

        if self.instance and self.instance.pk:
            for field in self._PRESERVE_IF_EMPTY:
                if not getattr(config, field):
                    original = self._original_values.get(field)
                    if original:
                        setattr(config, field, original)

        smtp_configured = (
            config.smtp_host and config.smtp_port and
            config.smtp_username and config.smtp_password and
            config.smtp_from_email
        )
        if smtp_configured:
            try:
                send_mail(
                    subject='系统配置测试邮件',
                    message='这是一封测试邮件，用于验证系统邮件配置是否正确。',
                    from_email=config.smtp_from_email,
                    recipient_list=[config.smtp_username],
                    fail_silently=False,
                )
            except Exception as e:
                raise ValidationError(
                    f'邮件配置测试失败: {str(e)}'
                )

        if commit:
            config.save()
        return config
