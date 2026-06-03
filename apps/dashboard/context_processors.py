from .models import SystemConfig


def system_config(request):
    try:
        config = SystemConfig.get_config()
    except Exception:
        config = None

    hostname = request.get_host().split(':')[0] if request else ''

    site_group = getattr(request, 'site_group', None)

    if site_group and site_group.site_name:
        site_name = site_group.site_name
    elif config:
        site_name = config.get_site_name_for_hostname(hostname)
    else:
        site_name = '2c2a'

    if site_group and site_group.site_icon:
        site_icon = site_group.site_icon
    elif config:
        site_icon = config.get_site_icon_for_hostname(hostname)
    else:
        site_icon = '/static/img/favicon.svg'

    is_site_group_admin = False
    if request.user.is_authenticated:
        is_site_group_admin = request.user.is_site_group_admin(site_group)

    return {
        'system_config': config,
        'site_name': site_name,
        'site_icon': site_icon,
        'site_group': site_group,
        'is_site_group_admin': is_site_group_admin,
    }
