"""
仪表盘视图
"""

from typing import Any
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib import messages

from apps.hosts.models import Host
from apps.operations.models import (
    AccountOpeningRequest,
    CloudComputerUser,
    Product,
    ProductGroup,
    ProductAccessGrant,
)
from apps.audit.models import AuditLog
from .models import DashboardWidget, SystemConfig
from .forms import SystemConfigForm
from utils.helpers import get_client_ip

User = get_user_model()


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    仪表盘主视图
    展示机器一览和注册主机入口
    """

    template_name = "dashboard/index.html"

    def get_context_data(self, **kwargs):
        """获取仪表盘上下文数据"""
        context = super().get_context_data(**kwargs)

        site_group = getattr(self.request, 'site_group', None)
        if site_group:
            product_groups = ProductGroup.objects.filter(
                is_active=True, site_group=site_group
            ).order_by(
                "display_order", "name"
            )
        else:
            product_groups = ProductGroup.objects.filter(is_active=True, site_group__isnull=True).order_by(
                "display_order", "name"
            )

        if site_group:
            products_qs = Product.objects.filter(
                is_available=True, site_group=site_group
            ).select_related(
                "host", "product_group"
            )
        else:
            products_qs = Product.objects.filter(is_available=True, site_group__isnull=True).select_related(
                "host", "product_group"
            )

        search = self.request.GET.get("search", "")
        if search:
            products_qs = products_qs.filter(
                Q(display_name__icontains=search)
                | Q(display_description__icontains=search)
                | Q(name__icontains=search)
            )

        status_filter = self.request.GET.get("status", "")
        if status_filter:
            products_qs = products_qs.filter(host__status=status_filter)

        group_filter = self.request.GET.get("group", "")
        if group_filter:
            products_qs = products_qs.filter(product_group_id=group_filter)

        auto_approval_filter = self.request.GET.get("auto_approval", "")
        if auto_approval_filter == "true":
            products_qs = products_qs.filter(auto_approval=True)
        elif auto_approval_filter == "false":
            products_qs = products_qs.filter(auto_approval=False)

        # 邀请访问权限过滤
        user = self.request.user
        if not user.is_staff and not user.is_superuser:
            # 获取用户有效的产品授权
            granted_product_ids = set(
                ProductAccessGrant.objects.filter(
                    user=user,
                    product__isnull=False,
                    is_revoked=False,
                ).exclude(
                    expires_at__lt=timezone.now()
                ).values_list('product_id', flat=True)
            )
            # 获取用户有效的产品组授权
            granted_group_ids = set(
                ProductAccessGrant.objects.filter(
                    user=user,
                    product_group__isnull=False,
                    is_revoked=False,
                ).exclude(
                    expires_at__lt=timezone.now()
                ).values_list('product_group_id', flat=True)
            )
            # 提供商可以看到自己创建的所有产品
            provider_created_ids = set()
            if hasattr(user, 'created_products'):
                provider_created_ids = set(
                    Product.objects.filter(created_by=user).values_list('id', flat=True)
                )

            # 过滤：公开产品 或 已授权产品 或 已授权产品组下的产品 或 提供商自己创建的产品
            products_qs = products_qs.filter(
                Q(visibility='public') |
                Q(id__in=granted_product_ids) |
                Q(product_group_id__in=granted_group_ids) |
                Q(id__in=provider_created_ids)
            )

        all_products = list(products_qs.order_by("-created_at"))

        user = self.request.user
        existing_cloud_users = {}
        if not (user.is_staff or user.is_superuser):
            cloud_user_qs = CloudComputerUser.objects.filter(
                Q(owner=user) | Q(created_from_request__applicant=user),
                status__in=['active', 'inactive', 'disabled'],
            ).values_list('product_id', 'pk')
            for product_id, cloud_user_pk in cloud_user_qs:
                if product_id not in existing_cloud_users:
                    existing_cloud_users[product_id] = cloud_user_pk

        pending_request_ids = {}
        if not (user.is_staff or user.is_superuser):
            request_qs = AccountOpeningRequest.objects.filter(
                applicant=user,
                status__in=['pending', 'approved', 'processing'],
            ).values_list('target_product_id', 'pk')
            for product_id, request_pk in request_qs:
                if product_id not in pending_request_ids:
                    pending_request_ids[product_id] = request_pk

        grouped_products: list[dict[str, Any]] = []
        for group in product_groups:
            products = [p for p in all_products if p.product_group_id == group.id]
            if products:
                grouped_products.append({"group": group, "products": products})

        ungrouped = [p for p in all_products if p.product_group_id is None]
        if ungrouped:
            grouped_products.append({"group": None, "products": ungrouped})

        context["existing_cloud_users"] = existing_cloud_users
        context["pending_request_ids"] = pending_request_ids

        context["grouped_products"] = grouped_products

        context["products"] = all_products

        context["public_hosts"] = all_products

        context["product_groups"] = product_groups
        context["status_choices"] = Host._meta.get_field("status").choices
        context["search"] = search
        context["status_filter"] = status_filter
        context["group_filter"] = group_filter
        context["auto_approval_filter"] = auto_approval_filter

        if site_group:
            stats = AccountOpeningRequest.objects.filter(
                target_product__site_group=site_group
            ).aggregate(
                pending_count=Count("id", filter=Q(status="pending")),
            )
            context["cloud_users_total"] = CloudComputerUser.objects.filter(
                product__site_group=site_group
            ).count()
        else:
            stats = AccountOpeningRequest.objects.filter(target_product__site_group__isnull=True).aggregate(
                pending_count=Count("id", filter=Q(status="pending")),
            )
            context["cloud_users_total"] = CloudComputerUser.objects.filter(product__site_group__isnull=True).count()
        context["account_requests_pending"] = stats["pending_count"]

        if self.request.user.is_staff or self.request.user.is_superuser:
            if site_group:
                context["account_requests_recent"] = (
                    AccountOpeningRequest.objects.filter(
                        target_product__site_group=site_group
                    ).select_related(
                        "applicant", "target_product", "target_product__host"
                    ).order_by("-created_at")[:5]
                )
            else:
                context["account_requests_recent"] = (
                    AccountOpeningRequest.objects.filter(target_product__site_group__isnull=True).select_related(
                        "applicant", "target_product", "target_product__host"
                    ).order_by("-created_at")[:5]
                )
        else:
            if site_group:
                context["account_requests_recent"] = AccountOpeningRequest.objects.filter(
                    applicant=self.request.user,
                ).filter(
                    target_product__site_group=site_group
                ).select_related(
                    "applicant", "target_product", "target_product__host"
                ).order_by("-created_at")[:5]
            else:
                context["account_requests_recent"] = AccountOpeningRequest.objects.filter(
                    applicant=self.request.user, target_product__site_group__isnull=True
                ).select_related(
                    "applicant", "target_product", "target_product__host"
                ).order_by("-created_at")[:5]

        try:
            AuditLog.objects.create(
                user=self.request.user,
                action="dashboard_view",
                description="访问仪表盘",
                ip_address=get_client_ip(self.request),
                user_agent=self.request.META.get("HTTP_USER_AGENT", ""),
            )
        except Exception:
            pass

        return context


class StatsAPIView(LoginRequiredMixin, View):
    """提供JSON格式的统计数据"""

    def get(self, request, *args, **kwargs):
        """获取统计数据"""
        stats_type = request.GET.get("type", "all")
        site_group = getattr(request, 'site_group', None)

        if stats_type == "all":
            data = self._get_all_stats(site_group)
        elif stats_type == "hosts":
            data = self._get_host_stats(site_group)
        elif stats_type == "operations":
            data = self._get_operation_stats()
        elif stats_type == "users":
            data = self._get_user_stats()
        elif stats_type == "account_opening":
            data = self._get_account_opening_stats(site_group)
        else:
            data = {"error": "Invalid stats type"}

        return JsonResponse(data)

    def _get_all_stats(self, site_group):
        """获取所有统计数据"""
        return {
            "hosts": self._get_host_stats(site_group),
            "operations": self._get_operation_stats(),
            "users": self._get_user_stats(),
            "account_opening": self._get_account_opening_stats(site_group),
        }

    def _get_host_stats(self, site_group):
        """获取主机统计"""
        from django.db.models import Count, Q
        if site_group:
            host_qs = Host.objects.filter(site_group=site_group)
        else:
            host_qs = Host.objects.filter(site_group__isnull=True)
        stats = host_qs.aggregate(
            total=Count('id'),
            online=Count('id', filter=Q(status='online')),
            offline=Count('id', filter=Q(status='offline')),
            error=Count('id', filter=Q(status='error')),
        )
        by_type = dict(
            host_qs.values("connection_type")
            .annotate(count=Count("id"))
            .values_list("connection_type", "count")
        )
        stats["by_type"] = by_type
        return stats

    def _get_operation_stats(self):
        """获取操作统计"""
        # 由于已移除 OperationLog，返回空统计
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "recent_7_days": 0,
            "by_type": {},
        }

    def _get_user_stats(self):
        """获取用户统计"""
        from django.db.models import Count, Q
        seven_days_ago = timezone.now() - timedelta(days=7)

        return User.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            recent_7_days=Count('id', filter=Q(date_joined__gte=seven_days_ago)),
        )

    def _get_account_opening_stats(self, site_group):
        """获取开户统计"""
        from django.db.models import Count, Q

        if site_group:
            request_qs = AccountOpeningRequest.objects.filter(
                target_product__site_group=site_group
            )
            cloud_qs = CloudComputerUser.objects.filter(
                product__site_group=site_group
            )
        else:
            request_qs = AccountOpeningRequest.objects.filter(target_product__site_group__isnull=True)
            cloud_qs = CloudComputerUser.objects.filter(product__site_group__isnull=True)
        request_stats = request_qs.aggregate(
            requests_total=Count('id'),
            requests_pending=Count('id', filter=Q(status='pending')),
            requests_approved=Count('id', filter=Q(status='approved')),
            requests_completed=Count('id', filter=Q(status='completed')),
            requests_failed=Count('id', filter=Q(status='failed')),
        )
        cloud_user_stats = cloud_qs.aggregate(
            cloud_users_total=Count('id'),
            cloud_users_active=Count('id', filter=Q(status='active')),
        )
        return {**request_stats, **cloud_user_stats}


class SystemConfigView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    """
    系统配置视图
    仅限管理员访问
    """

    template_name = "dashboard/system_config.html"

    def test_func(self):
        """检查用户是否为管理员"""
        return (
            self.request.user.is_staff or self.request.user.is_superuser
        )  # type: ignore

    def handle_no_permission(self):
        """处理无权限访问的情况"""
        messages.error(self.request, "您没有权限访问系统配置页面")
        return redirect("dashboard:index")

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        # 获取或创建系统配置
        config = SystemConfig.get_config()
        context["form"] = SystemConfigForm(instance=config)
        return context

    def post(self, request, *args, **kwargs):
        """处理系统配置更新"""
        config = SystemConfig.get_config()
        form = SystemConfigForm(request.POST, instance=config)

        if form.is_valid():
            form.save()
            messages.success(request, "系统配置已更新")

            AuditLog.objects.create(
                user=request.user,
                action="system_config_update",
                description="更新系统配置",
                ip_address=get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )

            return redirect("dashboard:index")
        else:
            messages.error(request, "系统配置更新失败，请检查表单中的错误")
            context = self.get_context_data()
            context["form"] = form
            return self.render_to_response(context)


class WidgetConfigView(LoginRequiredMixin, View):
    """
    仪表盘组件配置视图
    用于管理仪表盘组件的显示和配置
    """

    def get(self, request, *args, **kwargs):
        """渲染组件配置页面"""
        widgets = DashboardWidget.objects.all()
        context = {"widgets": widgets}
        return render(request, "dashboard/widget_config.html", context)

    def post(self, request, *args, **kwargs):
        """更新组件配置"""
        import json

        try:
            data = json.loads(request.body)
            widgets_data = data.get("widgets", [])

            for widget_data in widgets_data:
                widget_id = widget_data.get("widget_id")
                is_enabled = widget_data.get("is_enabled", False)
                display_order = widget_data.get("display_order", 0)

                try:
                    widget = DashboardWidget.objects.get(id=widget_id)
                    widget.is_enabled = is_enabled
                    widget.display_order = display_order
                    widget.save()
                except DashboardWidget.DoesNotExist:
                    return JsonResponse(
                        {"status": "error", "message": f"Widget {widget_id} not found"},
                        status=404,
                    )

            return JsonResponse({"status": "success"})
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON data"}, status=400
            )
