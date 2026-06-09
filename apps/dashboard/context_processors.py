from .models import SystemConfig
from utils.site_group import get_effective_config


def system_config(request):
    try:
        config = SystemConfig.get_config()
    except Exception:
        config = None

    site_group = getattr(request, "site_group", None)
    effective_config = get_effective_config(site_group) if config else None

    if effective_config and effective_config.site_name:
        site_name = effective_config.site_name
    elif site_group and site_group.site_name:
        site_name = site_group.site_name
    else:
        site_name = "2c2a"

    site_icon = None
    if effective_config and effective_config.site_icon:
        site_icon = effective_config.site_icon
    elif site_group and site_group.site_icon:
        site_icon = site_group.site_icon
    if not site_icon and effective_config:
        hostname = request.get_host().split(":")[0] if request else ""
        site_icon = effective_config.get_site_icon_for_hostname(hostname)
    if not site_icon:
        site_icon = "/static/img/favicon.svg"

    is_site_group_admin = False
    if request.user.is_authenticated:
        is_site_group_admin = request.user.is_site_group_admin(site_group)

    return {
        "system_config": config,
        "effective_config": effective_config,
        "site_name": site_name,
        "site_icon": site_icon,
        "site_group": site_group,
        "is_site_group_admin": is_site_group_admin,
    }
