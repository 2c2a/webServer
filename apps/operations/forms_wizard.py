"""
运营管理 - 产品向导式创建表单

分步引导超管创建产品，提供智能默认值和逐步验证。
与 AdminProductForm 不同，此表单专注于创建流程的简化和引导。
"""

import json

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Product, ProductGroup


_INPUT_CLASS = (
    "w-full bg-white/5 backdrop-blur-xl border border-white/10 rounded-md "
    "px-4 py-3 text-white placeholder-slate-500 "
    "focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition"
)
_SELECT_CLASS = (
    "w-full bg-white/5 backdrop-blur-xl border border-white/10 rounded-md "
    "px-4 py-3 text-white appearance-none "
    "focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 "
    "transition cursor-pointer"
)
_CHECKBOX_CLASS = (
    "w-5 h-5 rounded border-slate-700/50 bg-slate-900/50 "
    "text-cyan-400 focus:ring-cyan-500 focus:ring-2 transition cursor-pointer accent-md-primary"
)
_TEXTAREA_CLASS = (
    "w-full bg-white/5 backdrop-blur-xl border border-white/10 rounded-md "
    "px-4 py-3 text-white placeholder-slate-500 "
    "focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 "
    "transition resize-y"
)


class ProductWizardForm(forms.ModelForm):
    """
    产品创建向导表单

    分为三步：
    - Step 1: 基本信息 (display_name, display_description, product_group)
    - Step 2: 主机关联与配置 (host, display_hostname, rdp_port, visibility, is_available, auto_approval)
    - Step 3: 高级设置 (enable_host_protection, enable_disk_quota, default_disk_quota, allow_extra_quota_disks)

    智能默认值：
    - 选择主机后自动填充 display_hostname 和 rdp_port
    - 可见性默认为公开
    """

    default_disk_quota = forms.CharField(
        label=_("默认磁盘配额"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": '{"C:": 10240, "D:": 20480}',
                "class": _TEXTAREA_CLASS + " font-mono text-sm",
                "x-model": "defaultDiskQuota",
            }
        ),
        help_text=_(
            "每个磁盘的默认配额大小（MB），" 'JSON 格式，如 {"C:": 10240, "D:": 20480}'
        ),
    )

    allow_extra_quota_disks = forms.CharField(
        label=_("允许额外申请容量的磁盘"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": '["C:", "D:"]',
                "class": _TEXTAREA_CLASS + " font-mono text-sm",
                "x-model": "allowExtraQuotaDisks",
            }
        ),
        help_text=_(
            "允许用户在申请时额外申请容量的磁盘列表，" 'JSON 数组格式，如 ["C:", "D:"]'
        ),
    )

    class Meta:
        model = Product
        fields = [
            "display_name",
            "display_description",
            "product_group",
            "host",
            "is_available",
            "auto_approval",
            "visibility",
            "enable_host_protection",
            "display_hostname",
            "rdp_port",
            "enable_disk_quota",
            "limit_one_per_user",
        ]
        widgets = {
            "display_name": forms.TextInput(
                attrs={
                    "class": _INPUT_CLASS,
                    "placeholder": "输入产品显示名称",
                    "x-model": "displayName",
                    "required": "",
                }
            ),
            "display_description": forms.Textarea(
                attrs={
                    "class": _TEXTAREA_CLASS,
                    "rows": 3,
                    "placeholder": "输入产品显示描述（可选）",
                    "x-model": "displayDescription",
                }
            ),
            "product_group": forms.Select(
                attrs={
                    "class": _SELECT_CLASS,
                    "x-model": "productGroup",
                }
            ),
            "host": forms.Select(
                attrs={
                    "class": _SELECT_CLASS,
                    "x-model": "hostId",
                    "x-on:change": "onHostChange()",
                }
            ),
            "is_available": forms.CheckboxInput(
                attrs={
                    "class": _CHECKBOX_CLASS,
                    "x-model": "isAvailable",
                }
            ),
            "auto_approval": forms.CheckboxInput(
                attrs={
                    "class": _CHECKBOX_CLASS,
                    "x-model": "autoApproval",
                }
            ),
            "visibility": forms.Select(
                attrs={
                    "class": _SELECT_CLASS,
                    "x-model": "visibility",
                }
            ),
            "enable_host_protection": forms.CheckboxInput(
                attrs={
                    "class": _CHECKBOX_CLASS,
                    "x-model": "enableHostProtection",
                }
            ),
            "display_hostname": forms.TextInput(
                attrs={
                    "class": _INPUT_CLASS,
                    "placeholder": "输入显示地址",
                    "x-model": "displayHostname",
                    "required": "",
                }
            ),
            "rdp_port": forms.NumberInput(
                attrs={
                    "class": _INPUT_CLASS,
                    "placeholder": "3389",
                    "x-model.number": "rdpPort",
                }
            ),
            "enable_disk_quota": forms.CheckboxInput(
                attrs={
                    "class": _CHECKBOX_CLASS,
                    "x-model": "enableDiskQuota",
                }
            ),
            "limit_one_per_user": forms.CheckboxInput(
                attrs={
                    "class": _CHECKBOX_CLASS,
                    "x-model": "limitOnePerUser",
                }
            ),
        }
        labels = {
            "display_name": _("显示名称"),
            "display_description": _("显示描述"),
            "product_group": _("产品组"),
            "host": _("关联主机"),
            "is_available": _("是否可用"),
            "auto_approval": _("自动审核"),
            "visibility": _("可见性"),
            "enable_host_protection": _("启用主机保护(Gateway)"),
            "display_hostname": _("显示地址"),
            "rdp_port": _("RDP端口"),
            "enable_disk_quota": _("启用磁盘配额管理"),
            "limit_one_per_user": _("每人限购一个"),
        }
        help_texts = {
            "host": _("此产品运行所在的主机"),
            "is_available": _("是否在前端展示此产品"),
            "auto_approval": _("是否自动批准针对此产品的开户申请"),
            "visibility": _("公开对所有用户可见，" "邀请访问仅对已授权用户可见"),
            "enable_host_protection": _(
                "启用后，用户只能通过Gateway隧道访问RDP，"
                "主机不暴露公网IP。需部署Gateway服务。"
            ),
            "enable_disk_quota": _(
                "是否启用磁盘配额管理，" "启用后将自动为新用户设置磁盘配额"
            ),
            "limit_one_per_user": _("启用后，每个用户只能拥有一个此产品"),
        }

    def __init__(self, *args, user=None, site_group=None, **kwargs):
        super().__init__(*args, **kwargs)

        from apps.hosts.models import Host
        from utils.provider import get_provider_hosts
        from django.db.models import Q

        if user and user.is_superuser:
            host_qs = Host.objects.all()
            pg_qs = ProductGroup.objects.all()
        elif user and site_group and user.is_site_group_admin(site_group):
            host_qs = Host.objects.filter(site_group=site_group)
            pg_qs = ProductGroup.objects.filter(site_group=site_group)
        elif user:
            host_qs = get_provider_hosts(user, site_group=site_group)
            pg_qs = ProductGroup.objects.filter(created_by=user)
        else:
            host_qs = Host.objects.all()
            pg_qs = ProductGroup.objects.all()

        self.fields["host"].queryset = host_qs.order_by("name")
        self.fields["product_group"].queryset = pg_qs.order_by("name")

        if not self.initial.get("rdp_port"):
            self.initial["rdp_port"] = 3389
        if not self.initial.get("visibility"):
            self.initial["visibility"] = "public"

    def get_hosts_info(self):
        """
        返回主机列表信息，用于向导第二步的智能填充。
        包含主机ID、名称、地址、RDP端口等。
        """
        hosts = self.fields["host"].queryset
        result = []
        for host in hosts:
            result.append(
                {
                    "id": host.pk,
                    "name": host.name,
                    "hostname": host.hostname,
                    "rdp_port": host.rdp_port or 3389,
                    "connection_type": host.connection_type,
                    "status": host.status,
                }
            )
        return result

    def clean_default_disk_quota(self):
        data = self.cleaned_data.get("default_disk_quota", "")
        if not data or not data.strip():
            return {}
        if isinstance(data, dict):
            return data
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError("磁盘配额格式无效，请输入有效的 JSON")
        if not isinstance(parsed, dict):
            raise forms.ValidationError('磁盘配额必须为字典格式，如 {"C:": 10240}')
        for disk, value in parsed.items():
            try:
                val = int(value)
                if val < 0:
                    raise forms.ValidationError(f"磁盘 {disk} 的配额不能为负数")
            except (ValueError, TypeError):
                raise forms.ValidationError(f"磁盘 {disk} 的配额必须为数字")
        return parsed

    def clean_allow_extra_quota_disks(self):
        data = self.cleaned_data.get("allow_extra_quota_disks", "")
        if not data or not data.strip():
            return []
        if isinstance(data, list):
            return data
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            raise forms.ValidationError("磁盘列表格式无效，请输入有效的 JSON 数组")
        if not isinstance(parsed, list):
            raise forms.ValidationError('磁盘列表必须为数组格式，如 ["C:", "D:"]')
        return parsed

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.default_disk_quota = self.cleaned_data.get("default_disk_quota", {})
        instance.allow_extra_quota_disks = self.cleaned_data.get(
            "allow_extra_quota_disks", []
        )
        if commit:
            instance.save()
        return instance
