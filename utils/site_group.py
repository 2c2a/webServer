def get_site_group_queryset(
    user, model_class, site_group=None, filter_field='created_by'
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


def _get_provider_queryset(user, model_class, filter_field='created_by'):
    qs = model_class.objects.filter(**{filter_field: user})
    if hasattr(model_class, 'providers'):
        qs = qs | model_class.objects.filter(providers=user)
        qs = qs.distinct()
    return qs
