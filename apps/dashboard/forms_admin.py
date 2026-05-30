from django import forms
from .models import DashboardWidget, SystemConfig


class DashboardWidgetForm(forms.ModelForm):

    class Meta:
        model = DashboardWidget
        fields = [
            'widget_type', 'title', 'display_order',
            'is_enabled', 'widget_config',
        ]

    def clean_widget_config(self):
        import json
        config = self.cleaned_data.get('widget_config')
        if config:
            if isinstance(config, str):
                try:
                    json.loads(config)
                except json.JSONDecodeError:
                    raise forms.ValidationError('配置参数必须是有效的 JSON 格式')
        return config


class SystemConfigForm(forms.ModelForm):

    _PRESERVE_IF_EMPTY = [
        'smtp_password',
    ]

    class Meta:
        model = SystemConfig
        fields = [
            'site_name',
            'enable_registration',
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
            'local_access_locked',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_values = {}
        if self.instance and self.instance.pk:
            for field in self._PRESERVE_IF_EMPTY:
                self._original_values[field] = getattr(self.instance, field)
            for field in self._PRESERVE_IF_EMPTY:
                self.fields[field].required = False

    def clean_smtp_port(self):
        port = self.cleaned_data.get('smtp_port')
        if port and (port < 1 or port > 65535):
            raise forms.ValidationError('端口号必须在 1-65535 之间')
        return port

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.instance and self.instance.pk:
            for field in self._PRESERVE_IF_EMPTY:
                if not getattr(instance, field):
                    original = self._original_values.get(field)
                    if original:
                        setattr(instance, field, original)
        if commit:
            instance.save()
        return instance
