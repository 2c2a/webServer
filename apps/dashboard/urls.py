"""
仪表盘URL配置
"""

from django.urls import path
from . import views
from . import views_sitegroup
from . import views_sitegroup_users

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="index"),
    path("widget-config/", views.WidgetConfigView.as_view(), name="widget_config"),
    path("api/stats/", views.StatsAPIView.as_view(), name="stats_api"),
    path(
        "api/widget-config/", views.WidgetConfigView.as_view(), name="widget_config_api"
    ),
    path("sitegroup/", views_sitegroup.sitegroup_list, name="sitegroup_list"),
    path(
        "sitegroup/create/", views_sitegroup.sitegroup_create, name="sitegroup_create"
    ),
    path(
        "sitegroup/<int:pk>/", views_sitegroup.sitegroup_detail, name="sitegroup_detail"
    ),
    path(
        "sitegroup/<int:pk>/update/",
        views_sitegroup.sitegroup_update,
        name="sitegroup_update",
    ),
    path(
        "sitegroup/<int:pk>/delete/",
        views_sitegroup.sitegroup_delete,
        name="sitegroup_delete",
    ),
    path(
        "sitegroup/<int:pk>/add-hostname/",
        views_sitegroup.sitegroup_add_hostname,
        name="sitegroup_add_hostname",
    ),
    path(
        "sitegroup/<int:pk>/remove-hostname/<int:hostname_pk>/",
        views_sitegroup.sitegroup_remove_hostname,
        name="sitegroup_remove_hostname",
    ),
    path(
        "sitegroup/<int:pk>/add-admin/",
        views_sitegroup.sitegroup_add_admin,
        name="sitegroup_add_admin",
    ),
    path(
        "sitegroup/<int:pk>/remove-admin/<int:user_pk>/",
        views_sitegroup.sitegroup_remove_admin,
        name="sitegroup_remove_admin",
    ),
    path(
        "sitegroup/<int:pk>/config/",
        views_sitegroup.sitegroup_config,
        name="sitegroup_config",
    ),
    # 站点组用户管理
    path(
        "sitegroup/users/",
        views_sitegroup_users.sitegroup_user_list,
        name="sitegroup_user_list",
    ),
    path(
        "sitegroup/users/<int:user_pk>/toggle-active/",
        views_sitegroup_users.sitegroup_user_toggle_active,
        name="sitegroup_user_toggle_active",
    ),
    path(
        "sitegroup/users/<int:user_pk>/reset-password/",
        views_sitegroup_users.sitegroup_user_reset_password,
        name="sitegroup_user_reset_password",
    ),
    path(
        "sitegroup/users/<int:user_pk>/remove/",
        views_sitegroup_users.sitegroup_user_remove,
        name="sitegroup_user_remove",
    ),
    # 站点组管理员配置（无需 pk，使用 request.site_group）
    path(
        "sitegroup/my-config/",
        views_sitegroup.sitegroup_my_config,
        name="sitegroup_my_config",
    ),
]
