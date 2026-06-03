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


class HostnameBrandingWidget(forms.Textarea):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('attrs', {})
        kwargs['attrs']['rows'] = 6
        kwargs['attrs']['class'] = (
            'w-full bg-white/5 backdrop-blur-xl border border-white/10 '
            'rounded-md px-4 py-3 text-white placeholder-slate-500 '
            'focus:outline-none focus:ring-1 focus:ring-cyan-500/50 '
            'focus:border-cyan-500 transition resize-y font-mono text-sm'
        )
        kwargs['attrs']['placeholder'] = (
            '{\n'
            '  "site-a.example.com": {\n'
            '    "site_name": "站点A",\n'
            '    "site_icon": "/media/branding/site-a-icon.svg"\n'
            '  },\n'
            '  "site-b.example.com": {\n'
            '    "site_name": "站点B",\n'
            '    "site_icon": "/media/branding/site-b-icon.svg"\n'
            '  }\n'
            '}'
        )
        super().__init__(*args, **kwargs)

    def format_value(self, value):
        import json
        if value and isinstance(value, dict):
            return json.dumps(value, indent=2, ensure_ascii=False)
        return super().format_value(value)


class SystemConfigForm(forms.ModelForm):

    _PRESERVE_IF_EMPTY = [
        'smtp_password',
    ]

    hostname_branding = forms.CharField(
        widget=HostnameBrandingWidget(),
        required=False,
        label='主机名品牌绑定',
        help_text=(
            '按主机名绑定专用站点名和图标，格式：\n'
            '{"host.example.com": {"site_name": "站点名", "site_icon": "/media/branding/icon.svg"}}\n'
            '未配置的主机名使用全局默认值\n\n'
            '⚠️ 此功能已由「站点组管理」替代，建议运行 python manage.py migrate_hostname_branding 迁移数据'
        ),
    )

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
            'hostname_branding',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_values = {}
        if self.instance and self.instance.pk:
            for field in self._PRESERVE_IF_EMPTY:
                self._original_values[field] = getattr(self.instance, field)
            for field in self._PRESERVE_IF_EMPTY:
                self.fields[field].required = False

    def clean_hostname_branding(self):
        import json
        value = self.cleaned_data.get('hostname_branding')
        if not value:
            return {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise forms.ValidationError('必须是有效的 JSON 格式')
        if not isinstance(value, dict):
            raise forms.ValidationError('必须是 JSON 对象格式')
        for hostname, config in value.items():
            if not isinstance(hostname, str) or not hostname.strip():
                raise forms.ValidationError(
                    f'主机名 "{hostname}" 无效'
                )
            if not isinstance(config, dict):
                raise forms.ValidationError(
                    f'主机名 "{hostname}" 的配置必须是对象'
                )
            allowed_keys = {'site_name', 'site_icon'}
            invalid_keys = set(config.keys()) - allowed_keys
            if invalid_keys:
                raise forms.ValidationError(
                    f'主机名 "{hostname}" 包含无效字段: '
                    f'{", ".join(invalid_keys)}，'
                    f'仅支持: {", ".join(allowed_keys)}'
                )
        return value

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
