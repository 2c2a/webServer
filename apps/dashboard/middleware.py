from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import resolve


class SiteGroupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.site_group = self._resolve_site_group(request)
        response = self._check_pending_migration(request)
        if response:
            return response
        response = self._check_banned_user(request)
        if response:
            return response
        return self.get_response(request)

    def _check_pending_migration(self, request):
        """已登录用户有 pending_migration_sg_id 时，强制跳转迁移页"""
        if not request.user.is_authenticated:
            return None
        sg_id = request.session.get("pending_migration_sg_id")
        if not sg_id:
            return None
        # 跳过静态文件和媒体文件
        if request.path.startswith("/static/") or request.path.startswith("/media/"):
            return None
        try:
            match = resolve(request.path)
            # 允许访问迁移页、登出、邮箱绑定相关 API
            allowed_names = (
                "migrate",
                "logout",
                "email_bind",
                "send_bind_email_code",
                "email_list",
                "email_set_primary",
                "email_unbind",
                "email_merge_confirm",
            )
            if match.url_name in allowed_names:
                return None
        except Exception:
            pass
        return redirect("accounts:migrate")

    def _check_banned_user(self, request):
        """封禁用户只能访问封禁提示页和工单相关页面"""
        if not request.user.is_authenticated:
            return None
        # 使用自定义 UserBan 模型判断封禁状态
        from apps.accounts.models import UserBan
        if not UserBan.objects.filter(user=request.user).exists():
            return None
        # 静态文件和媒体文件放行
        if request.path.startswith("/static/") or request.path.startswith("/media/"):
            return None
        try:
            match = resolve(request.path)
            # 允许访问封禁提示页、登出、工单相关页面
            allowed_names = (
                "banned",
                "logout",
                "ticket_list",
                "ticket_create",
                "ticket_detail",
                "my_tickets",
                "ticket_comment",
            )
            if match.url_name in allowed_names:
                return None
            # 允许工单 app 的所有视图
            if match.app_name == "tickets":
                return None
        except Exception:
            pass
        return redirect("accounts:banned")

    def _resolve_site_group(self, request):
        try:
            hostname = request.get_host().split(":")[0]
        except Exception:
            return None

        if not hostname:
            return None

        cache_key = f"site_group:hostname:{hostname}"
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
            mapping = SiteGroupHostname.objects.select_related("site_group").get(
                hostname=hostname
            )
        except SiteGroupHostname.DoesNotExist:
            cache.set(cache_key, 0, timeout=300)
            return None

        site_group = mapping.site_group
        if not site_group.is_active:
            cache.set(cache_key, 0, timeout=300)
            return None

        cache.set(cache_key, site_group.pk, timeout=300)
        return site_group
