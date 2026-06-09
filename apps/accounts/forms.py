"""
用户管理表单
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from .models import UserProfile
from config.demo_middleware import is_demo_mode

User = get_user_model()

MD_INPUT_CLASS = (
    "w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 "
    "text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 "
    "focus:ring-md-primary transition"
)
MD_SELECT_CLASS = (
    "w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 "
    "text-md-on-surface appearance-none focus:outline-none focus:ring-2 "
    "focus:ring-md-primary transition cursor-pointer"
)
MD_CHECKBOX_CLASS = (
    "w-5 h-5 rounded border-md-outline/50 bg-md-surface/50 text-md-primary "
    "focus:ring-md-primary focus:ring-2 transition cursor-pointer accent-md-primary"
)


class UserRegistrationForm(UserCreationForm):
    """用户注册表单"""

    email = forms.EmailField(
        required=True,
        label=_("邮箱"),
        widget=forms.EmailInput(
            attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入邮箱地址")}
        ),
    )
    email_code = forms.CharField(
        required=True,
        label=_("邮箱验证码"),
        widget=forms.TextInput(
            attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入邮箱收到的验证码")}
        ),
    )
    # 移除不需要的confirm_password字段，因为UserCreationForm使用password1和password2
    agree_terms = forms.BooleanField(
        required=True,
        label=_("我已阅读并同意服务条款和隐私政策"),
        widget=forms.CheckboxInput(attrs={"class": MD_CHECKBOX_CLASS}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        widgets = {
            "username": forms.TextInput(
                attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入用户名")}
            ),
        }

    def clean_password1(self):
        """在DEMO模式下，对密码不做复杂度要求"""
        import os

        password = self.cleaned_data.get("password1")
        if os.environ.get("2C2A_DEMO", "").lower() == "1":
            # 在DEMO模式下，接受任何密码
            return password
        else:
            # 在非DEMO模式下，保持原有验证逻辑
            return password

    def clean_password2(self):
        """在DEMO模式下，对密码不做复杂度要求"""
        import os

        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError(_("两次输入的密码不一致"))

        if os.environ.get("2C2A_DEMO", "").lower() == "1":
            # 在DEMO模式下，接受任何密码
            return password2
        else:
            # 在非DEMO模式下，保持原有验证逻辑
            return password2

    def clean_email(self):
        """验证邮箱后缀"""
        email = self.cleaned_data.get("email")

        from utils.site_group import get_effective_config

        ec = get_effective_config()

        if not ec.is_email_suffix_allowed(email):
            email_suffix = "@" + email.split("@")[1] if "@" in email else ""
            suffix_data = ec.get_email_suffix_lists()
            if suffix_data["whitelist"]:
                raise forms.ValidationError(f"邮箱后缀 {email_suffix} 不在允许的列表中")
            else:
                raise forms.ValidationError(f"邮箱后缀 {email_suffix} 已被禁止使用")

        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError

        try:
            validate_email(email)
        except ValidationError:
            raise forms.ValidationError("请输入有效的邮箱地址")

        from django.contrib.auth import get_user_model

        User = get_user_model()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("该邮箱已被注册")

        return email

    def clean_agree_terms(self):
        """验证用户是否同意条款"""
        agree_terms = self.cleaned_data.get("agree_terms")
        if not agree_terms:
            raise forms.ValidationError(_("您必须同意服务条款和隐私政策才能注册"))
        return agree_terms

    def save(self, commit=True):
        """保存用户"""
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            # 创建用户资料
            from .models import UserProfile

            UserProfile.objects.create(user=user)
        return user


class UserUpdateForm(forms.ModelForm):
    """用户信息更新表单"""

    class Meta:
        model = User
        fields = ("username", "email")
        widgets = {
            "username": forms.TextInput(
                attrs={"class": MD_INPUT_CLASS, "readonly": "readonly"}
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": MD_INPUT_CLASS,
                    "readonly": "readonly",  # 邮箱不允许修改
                }
            ),
        }


class DemoPasswordChangeForm(PasswordChangeForm):
    """DEMO模式下的密码更改表单 - 禁止更改密码"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if is_demo_mode():
            # 在DEMO模式下，禁用所有字段
            for field_name in self.fields:
                self.fields[field_name].widget.attrs["disabled"] = True
            # 添加错误信息
            self.fields["old_password"].help_text = "DEMO模式下不允许修改密码"

    def clean(self):
        """验证表单"""
        cleaned_data = super().clean()

        if is_demo_mode():
            raise forms.ValidationError("DEMO模式下不允许修改密码")

        return cleaned_data


class UserLoginForm(forms.Form):
    """用户登录表单"""

    username = forms.CharField(
        label=_("用户名"),
        widget=forms.TextInput(
            attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入用户名")}
        ),
    )
    password = forms.CharField(
        label=_("密码"),
        widget=forms.PasswordInput(
            attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入密码")}
        ),
    )
    remember = forms.BooleanField(
        required=False,
        label=_("记住我"),
        widget=forms.CheckboxInput(attrs={"class": MD_CHECKBOX_CLASS}),
    )


class UserProfileForm(forms.ModelForm):
    """用户资料表单"""

    class Meta:
        model = UserProfile
        fields = (
            "nickname",
            "gender",
            "birthday",
            "location",
            "bio",
            "email_notification",
            "system_notification",
        )
        widgets = {
            "nickname": forms.TextInput(
                attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入昵称")}
            ),
            "gender": forms.Select(attrs={"class": MD_SELECT_CLASS}),
            "birthday": forms.DateInput(
                attrs={"class": MD_INPUT_CLASS, "type": "date"}
            ),
            "location": forms.TextInput(
                attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入所在地")}
            ),
            "bio": forms.Textarea(
                attrs={
                    "class": MD_INPUT_CLASS,
                    "rows": 4,
                    "placeholder": _("请输入个人简介"),
                }
            ),
            "email_notification": forms.CheckboxInput(
                attrs={"class": MD_CHECKBOX_CLASS}
            ),
            "system_notification": forms.CheckboxInput(
                attrs={"class": MD_CHECKBOX_CLASS}
            ),
        }


class PasswordChangeForm(forms.Form):
    """密码修改表单"""

    old_password = forms.CharField(
        label=_("当前密码"),
        widget=forms.PasswordInput(
            attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入当前密码")}
        ),
    )
    new_password = forms.CharField(
        label=_("新密码"),
        widget=forms.PasswordInput(
            attrs={"class": MD_INPUT_CLASS, "placeholder": _("请输入新密码")}
        ),
        min_length=8,
    )
    confirm_password = forms.CharField(
        label=_("确认密码"),
        widget=forms.PasswordInput(
            attrs={"class": MD_INPUT_CLASS, "placeholder": _("请再次输入新密码")}
        ),
        min_length=8,
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password and confirm_password and new_password != confirm_password:
            raise forms.ValidationError(_("两次输入的密码不一致"))

        return cleaned_data
