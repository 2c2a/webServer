from django import forms
from .models import SiteGroup, SiteGroupHostname, SiteGroupConfig


GLOW_INPUT = (
    "w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 "
    "rounded px-3 py-2 text-slate-200 placeholder-slate-500 "
    "focus:outline-none focus:ring-1 focus:ring-cyan-500/50 "
    "focus:border-cyan-500 transition"
)
GLOW_SELECT = (
    "w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 "
    "rounded px-3 py-2 text-slate-200 appearance-none "
    "focus:outline-none focus:ring-1 focus:ring-cyan-500/50 "
    "focus:border-cyan-500 transition cursor-pointer"
)
GLOW_TEXTAREA = (
    "w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 "
    "rounded px-3 py-2 text-slate-200 placeholder-slate-500 "
    "focus:outline-none focus:ring-1 focus:ring-cyan-500/50 "
    "focus:border-cyan-500 transition font-mono text-sm"
)
GLOW_CHECKBOX = (
    "w-4 h-4 bg-slate-900/50 border-slate-700/50 rounded "
    "focus:ring-cyan-500/50 text-cyan-500"
)


class SiteGroupForm(forms.ModelForm):
    class Meta:
        model = SiteGroup
        fields = ["name", "slug", "description", "site_name", "site_icon", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": GLOW_INPUT}),
            "slug": forms.TextInput(attrs={"class": GLOW_INPUT}),
            "description": forms.Textarea(
                attrs={
                    "class": GLOW_INPUT,
                    "rows": 3,
                }
            ),
            "site_name": forms.TextInput(attrs={"class": GLOW_INPUT}),
            "site_icon": forms.TextInput(attrs={"class": GLOW_INPUT}),
            "is_active": forms.CheckboxInput(attrs={"class": GLOW_CHECKBOX}),
        }


class SiteGroupHostnameForm(forms.ModelForm):
    class Meta:
        model = SiteGroupHostname
        fields = ["hostname"]
        widgets = {
            "hostname": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "demo.example.com",
                }
            ),
        }


class SiteGroupConfigForm(forms.ModelForm):
    """站点组配置覆盖表单"""

    class Meta:
        model = SiteGroupConfig
        fields = [
            "site_name",
            "site_icon",
            "icp_number",
            "police_number",
            "smtp_host",
            "smtp_port",
            "smtp_encryption",
            "smtp_username",
            "smtp_password",
            "smtp_from_email",
            "smtp_from_name",
            "captcha_provider",
            "captcha_type",
            "login_captcha_type",
            "register_captcha_type",
            "email_captcha_type",
            "enable_registration",
            "email_suffix_whitelist",
            "email_suffix_blacklist",
        ]
        widgets = {
            "site_name": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "site_icon": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置，如 /media/branding/icon.svg",
                }
            ),
            "icp_number": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "police_number": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "smtp_host": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "smtp_port": forms.NumberInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "smtp_encryption": forms.Select(attrs={"class": GLOW_SELECT}),
            "smtp_username": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "smtp_password": forms.PasswordInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空保持原值",
                }
            ),
            "smtp_from_email": forms.EmailInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "smtp_from_name": forms.TextInput(
                attrs={
                    "class": GLOW_INPUT,
                    "placeholder": "留空使用全局配置",
                }
            ),
            "captcha_provider": forms.Select(attrs={"class": GLOW_SELECT}),
            "captcha_type": forms.Select(attrs={"class": GLOW_SELECT}),
            "login_captcha_type": forms.Select(attrs={"class": GLOW_SELECT}),
            "register_captcha_type": forms.Select(attrs={"class": GLOW_SELECT}),
            "email_captcha_type": forms.Select(attrs={"class": GLOW_SELECT}),
            "enable_registration": forms.Select(
                attrs={
                    "class": GLOW_SELECT,
                },
                choices=[
                    ("", "--- 使用全局配置 ---"),
                    ("true", "启用"),
                    ("false", "禁用"),
                ],
            ),
            "email_suffix_whitelist": forms.Textarea(
                attrs={
                    "class": GLOW_TEXTAREA,
                    "rows": 4,
                    "placeholder": "留空使用全局配置\n@example.com\n@gmail.com",
                }
            ),
            "email_suffix_blacklist": forms.Textarea(
                attrs={
                    "class": GLOW_TEXTAREA,
                    "rows": 4,
                    "placeholder": "留空使用全局配置\n@tempmail.com\n@spam.com",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 为验证码类型字段添加"使用全局配置"空选项
        for field_name in [
            "captcha_type",
            "login_captcha_type",
            "register_captcha_type",
            "email_captcha_type",
        ]:
            self.fields[field_name].widget.choices = [
                ("", "--- 使用全局配置 ---"),
            ] + list(self.fields[field_name].widget.choices)

    def clean_smtp_password(self):
        """密码字段留空时保留原值"""
        password = self.cleaned_data.get("smtp_password")
        if not password and self.instance and self.instance.pk:
            return self.instance.smtp_password
        return password
