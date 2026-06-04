from django.core.cache import cache


class SiteGroupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.site_group = self._resolve_site_group(request)
        return self.get_response(request)

    def _resolve_site_group(self, request):
        try:
            hostname = request.get_host().split(':')[0]
        except Exception:
            return None

        if not hostname:
            return None

        cache_key = f'site_group:hostname:{hostname}'
        site_group_id = cache.get(cache_key)

        if site_group_id is not None:
            if site_group_id == 0:
                return None
            from apps.dashboard.models import SiteGroup
            try:
                site_group = SiteGroup.objects.get(pk=site_group_id, is_active=True)
                return site_group
            except SiteGroup.DoesNotExist:
                cache.delete(cache_key)
                return None

        from apps.dashboard.models import SiteGroupHostname
        try:
            mapping = SiteGroupHostname.objects.select_related('site_group').get(hostname=hostname)
        except SiteGroupHostname.DoesNotExist:
            cache.set(cache_key, 0, timeout=300)
            return None

        site_group = mapping.site_group
        if not site_group.is_active:
            cache.set(cache_key, 0, timeout=300)
            return None

        cache.set(cache_key, site_group.pk, timeout=300)
        return site_group
