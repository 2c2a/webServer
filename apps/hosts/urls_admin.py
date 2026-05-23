"""
超管后台 - 主机管理 URL 配置

命名空间: admin_hosts (通过 admin: 命名空间访问)
超管可查看所有主机和主机组，无数据隔离。
"""

from django.urls import path

from . import views_admin

app_name = 'admin_hosts'

urlpatterns = [
    # 主机管理
    path(
        '',
        views_admin.AdminHostListView.as_view(),
        name='host_list'
    ),
    path(
        'wizard/',
        views_admin.admin_host_wizard,
        name='host_wizard'
    ),
    path(
        'wizard/generate-token/',
        views_admin.admin_host_wizard_generate_token,
        name='host_wizard_generate_token'
    ),
    path(
        'wizard/test-connection/',
        views_admin.admin_host_wizard_test_connection,
        name='host_wizard_test_connection'
    ),
    path(
        'wizard/generate-init-command/',
        views_admin.admin_host_wizard_generate_init_command,
        name='host_wizard_generate_init_command'
    ),
    path(
        'create/',
        views_admin.AdminHostCreateView.as_view(),
        name='host_create'
    ),
    path(
        '<int:pk>/',
        views_admin.AdminHostDetailView.as_view(),
        name='host_detail'
    ),
    path(
        '<int:pk>/edit/',
        views_admin.AdminHostUpdateView.as_view(),
        name='host_edit'
    ),
    path(
        '<int:pk>/delete/',
        views_admin.AdminHostDeleteView.as_view(),
        name='host_delete'
    ),
    path(
        '<int:pk>/test/',
        views_admin.admin_host_test_connection,
        name='host_test'
    ),
    path(
        '<int:pk>/generate-init-command/',
        views_admin.admin_host_generate_init_command,
        name='host_generate_init_command'
    ),

    # 主机组管理
    path(
        'groups/',
        views_admin.AdminHostGroupListView.as_view(),
        name='hostgroup_list'
    ),
    path(
        'groups/create/',
        views_admin.AdminHostGroupCreateView.as_view(),
        name='hostgroup_create'
    ),
    path(
        'groups/<int:pk>/edit/',
        views_admin.AdminHostGroupUpdateView.as_view(),
        name='hostgroup_edit'
    ),
    path(
        'groups/<int:pk>/delete/',
        views_admin.AdminHostGroupDeleteView.as_view(),
        name='hostgroup_delete'
    ),
]
