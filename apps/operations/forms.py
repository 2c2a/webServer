"""
操作记录表单
"""

import json
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SystemTask, AccountOpeningRequest, CloudComputerUser
from apps.hosts.models import Host


class SystemTaskFilterForm(forms.Form):
    """
    系统任务过滤表单
    """

    task_type = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "任务类型"}
        ),
        label=_("任务类型"),
    )

    status = forms.ChoiceField(
        required=False,
        choices=[("", "全部")] + SystemTask._meta.get_field("status").choices,
        widget=forms.Select(attrs={"class": "form-control"}),
        label=_("状态"),
    )

    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label=_("开始日期"),
    )

    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        label=_("结束日期"),
    )


class AccountOpeningRequestForm(forms.ModelForm):
    """
    用户开户申请表单
    """

    # 重写username字段以符合新需求
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "请输入主机连接用户名"}
        ),
        label=_("主机连接用户名"),
        help_text=_("将在云电脑主机上创建的连接用户名"),
    )

    # 重写user_fullname字段以符合新需求
    user_fullname = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "请输入显示用户名"}
        ),
        label=_("主机显示用户名"),
        help_text=_("用于在系统中显示的用户名"),
    )

    # 重写user_description字段以符合新需求
    user_description = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 4, "placeholder": "请输入申请理由"}
        ),
        label=_("申请理由"),
        help_text=_("请说明申请云电脑主机的用途和理由"),
    )

    target_product = forms.ModelChoiceField(
        queryset=None,  # 动态设置
        widget=forms.Select(attrs={"class": "form-control"}),
        label=_("目标产品"),
        help_text=_("请选择您要申请的产品"),
    )

    requested_disk_capacity = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
        label=_("需求磁盘容量"),
        help_text=_("额外申请的磁盘容量（MB）"),
    )

    class Meta:
        model = AccountOpeningRequest
        fields = [
            "username",
            "user_fullname",
            "user_description",
            "target_product",
            "requested_disk_capacity",
        ]

    def __init__(self, *args, **kwargs):
        # 从视图传入的产品查询集
        products_qs = kwargs.pop("products_qs", None)
        site_group = kwargs.pop("site_group", None)
        super().__init__(*args, **kwargs)

        if products_qs is not None:
            self.fields["target_product"].queryset = products_qs
        else:
            # 默认按 site_group 过滤可用产品
            from .models import Product

            qs = Product.objects.filter(is_available=True)
            if site_group:
                qs = qs.filter(site_group=site_group)
            else:
                qs = qs.filter(site_group__isnull=True)
            self.fields["target_product"].queryset = qs

        # 如果只有一个产品选项，将其设为初始值并隐藏
        if len(self.fields["target_product"].queryset) == 1:
            target_product = self.fields["target_product"].queryset.first()
            self.fields["target_product"].initial = target_product
            # 将字段设为隐藏
            self.fields["target_product"].widget = forms.HiddenInput()

    def clean_requested_disk_capacity(self):
        data = self.cleaned_data.get("requested_disk_capacity", "{}")
        if not data:
            return {}
        if isinstance(data, dict):
            return data
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError("磁盘容量格式无效")
        if not isinstance(parsed, dict):
            raise forms.ValidationError("磁盘容量必须为字典格式")
        for disk, value in parsed.items():
            try:
                val = int(value)
                if val < 0:
                    raise forms.ValidationError(f"磁盘 {disk} 的容量不能为负数")
            except (ValueError, TypeError):
                raise forms.ValidationError(f"磁盘 {disk} 的容量必须为数字")
        return parsed


class AccountOpeningRequestFilterForm(forms.Form):
    """
    开户申请过滤表单
    """

    status = forms.ChoiceField(
        required=False,
        choices=[("", "全部")]
        + AccountOpeningRequest._meta.get_field("status").choices,
        widget=forms.Select(attrs={"class": "form-control"}),
        label=_("状态"),
    )

    host = forms.ModelChoiceField(
        required=False,
        queryset=Host.objects.none(),
        widget=forms.Select(attrs={"class": "form-control"}),
        label=_("主机"),
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "搜索用户名、姓名或邮箱"}
        ),
        label=_("搜索"),
    )

    def __init__(self, *args, **kwargs):
        site_group = kwargs.pop("site_group", None)
        super().__init__(*args, **kwargs)
        if site_group:
            self.fields["host"].queryset = Host.objects.filter(site_group=site_group)
        else:
            self.fields["host"].queryset = Host.objects.filter(site_group__isnull=True)


class CloudComputerUserFilterForm(forms.Form):
    """
    云电脑用户过滤表单
    """

    status = forms.ChoiceField(
        required=False,
        choices=[("", "全部")] + CloudComputerUser._meta.get_field("status").choices,
        widget=forms.Select(attrs={"class": "form-control"}),
        label=_("状态"),
    )

    product = forms.ModelChoiceField(
        required=False,
        queryset=None,
        widget=forms.Select(attrs={"class": "form-control"}),
        label=_("产品"),
    )

    search = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "搜索用户名、姓名或邮箱"}
        ),
        label=_("搜索"),
    )

    def __init__(self, *args, **kwargs):
        site_group = kwargs.pop("site_group", None)
        super().__init__(*args, **kwargs)
        from .models import Product

        if site_group:
            self.fields["product"].queryset = Product.objects.filter(
                site_group=site_group
            )
        else:
            self.fields["product"].queryset = Product.objects.filter(
                site_group__isnull=True
            )
