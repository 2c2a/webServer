from django.core.cache import cache


# SiteGroupConfig 中可覆盖的字段名列表
OVERRIDABLE_FIELDS = [
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
    "site_name",
    "site_icon",
    "icp_number",
    "police_number",
]


class EffectiveConfig:
    """
    合并配置：优先使用 SiteGroupConfig 的非空字段，回退到 SystemConfig。

    用法:
        ec = get_effective_config(site_group)
        ec.smtp_host       # 优先站点组配置，回退全局配置
        ec.enable_registration
        ec.get_captcha_config(scene='login')
        ec.get_email_suffix_lists()
    """

    def __init__(self, system_config, site_group_config=None):
        self._system = system_config
        self._sg = site_group_config

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        # 优先站点组配置的非空值
        if self._sg is not None:
            sg_val = getattr(self._sg, name, None)
            if sg_val is not None and name in OVERRIDABLE_FIELDS:
                return sg_val
        # 回退全局配置
        return getattr(self._system, name, None)

    def get_captcha_config(self, scene=None):
        """根据场景获取验证码配置，与 SystemConfig.get_captcha_config 兼容"""
        provider = self.captcha_provider
        if scene == "login":
            captcha_type = self.login_captcha_type or self.captcha_type
        elif scene == "register":
            captcha_type = self.register_captcha_type or self.captcha_type
        elif scene == "email":
            captcha_type = self.email_captcha_type or self.captcha_type
        else:
            captcha_type = self.captcha_type
        return provider, captcha_type

    def get_email_suffix_lists(self):
        """获取邮箱后缀白名单和黑名单列表（已解析为列表）"""
        cache_key = f'effective_email_suffixes:{self._system.pk}:{getattr(self._sg, "pk", "none")}'
        data = cache.get(cache_key)
        if data is not None:
            return data

        whitelist = []
        if self.email_suffix_whitelist:
            whitelist = [
                s.strip()
                for s in self.email_suffix_whitelist.strip().split("\n")
                if s.strip()
            ]
        blacklist = []
        if self.email_suffix_blacklist:
            blacklist = [
                s.strip()
                for s in self.email_suffix_blacklist.strip().split("\n")
                if s.strip()
            ]
        data = {"whitelist": whitelist, "blacklist": blacklist}
        cache.set(cache_key, data, timeout=300)
        return data

    def is_email_suffix_allowed(self, email):
        """检查邮箱后缀是否符合当前配置"""
        suffix = "@" + email.split("@")[1] if "@" in email else ""
        data = self.get_email_suffix_lists()
        if data["whitelist"]:
            return suffix in data["whitelist"]
        if data["blacklist"]:
            return suffix not in data["blacklist"]
        return True


def get_effective_config(site_group=None):
    """
    获取合并后的有效配置。

    Args:
        site_group: SiteGroup 实例或 None。None 时返回纯全局配置。

    Returns:
        EffectiveConfig 实例
    """
    from apps.dashboard.models import SystemConfig, SiteGroupConfig

    system_config = SystemConfig.get_config()
    sg_config = SiteGroupConfig.get_config(site_group) if site_group else None
    return EffectiveConfig(system_config, sg_config)


def get_site_group_queryset(
    user, model_class, site_group=None, filter_field="created_by"
):
    if user.is_superuser:
        return model_class.objects.all()

    if _is_site_group_admin(user, site_group):
        return _filter_by_site_group(model_class, site_group)

    provider_qs = _get_provider_queryset(user, model_class, filter_field)
    site_group_qs = _filter_by_site_group(model_class, site_group)
    return provider_qs & site_group_qs


def _is_site_group_admin(user, site_group):
    if user.is_superuser:
        return True
    if site_group is None:
        return False
    return site_group.admins.filter(pk=user.pk).exists()


def _filter_by_site_group(model_class, site_group):
    if site_group is not None:
        return model_class.objects.filter(site_group=site_group)
    return model_class.objects.filter(site_group__isnull=True)


def _get_provider_queryset(user, model_class, filter_field="created_by"):
    qs = model_class.objects.filter(**{filter_field: user})
    if hasattr(model_class, "providers"):
        qs = qs | model_class.objects.filter(providers=user)
        qs = qs.distinct()
    return qs
