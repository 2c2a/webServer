"""
超管后台 - 运营管理 URL 配置

命名空间: admin_operations
超管可查看所有运营数据，无数据隔离。
"""

from django.urls import path

from . import views_admin

app_name = 'admin_operations'

urlpatterns = [
    # ========== 产品管理 ==========
    path('products/', views_admin.AdminProductListView.as_view(), name='product_list'),
    path('products/wizard/', views_admin.admin_product_wizard, name='product_wizard'),
    path('products/create/', views_admin.AdminProductCreateView.as_view(), name='product_create'),
    path('products/<int:pk>/edit/', views_admin.AdminProductUpdateView.as_view(), name='product_edit'),
    path('products/<int:pk>/delete/', views_admin.AdminProductDeleteView.as_view(), name='product_delete'),

    # ========== 产品组管理 ==========
    path('product-groups/', views_admin.AdminProductGroupListView.as_view(), name='productgroup_list'),
    path('product-groups/create/', views_admin.AdminProductGroupCreateView.as_view(), name='productgroup_create'),
    path('product-groups/<int:pk>/edit/', views_admin.AdminProductGroupUpdateView.as_view(), name='productgroup_edit'),
    path('product-groups/<int:pk>/delete/', views_admin.AdminProductGroupDeleteView.as_view(), name='productgroup_delete'),

    # ========== 开户申请管理 ==========
    path('requests/', views_admin.AdminRequestListView.as_view(), name='request_list'),
    path('requests/<int:pk>/', views_admin.AdminRequestDetailView.as_view(), name='request_detail'),
    path('requests/<int:pk>/approve/', views_admin.AdminRequestApproveView.as_view(), name='request_approve'),
    path('requests/<int:pk>/reject/', views_admin.AdminRequestRejectView.as_view(), name='request_reject'),
    path('requests/<int:pk>/retry/', views_admin.AdminRequestRetryView.as_view(), name='request_retry'),
    path('requests/batch-approve/', views_admin.AdminRequestBatchApproveView.as_view(), name='request_batch_approve'),
    path('requests/batch-reject/', views_admin.AdminRequestBatchRejectView.as_view(), name='request_batch_reject'),

    # ========== 云电脑用户管理 ==========
    path('users/', views_admin.AdminCloudUserListView.as_view(), name='user_list'),
    path('users/<int:pk>/', views_admin.AdminCloudUserDetailView.as_view(), name='user_detail'),
    path('users/<int:pk>/action/', views_admin.admin_cloud_user_action, name='user_action'),
    path('users/<int:pk>/set-quota/', views_admin.admin_cloud_user_set_quota, name='user_set_quota'),

    # ========== 邀请令牌管理 ==========
    path('tokens/', views_admin.AdminTokenListView.as_view(), name='token_list'),
    path('tokens/<int:pk>/', views_admin.AdminTokenDetailView.as_view(), name='token_detail'),

    # ========== 访问授权管理 ==========
    path('grants/', views_admin.AdminGrantListView.as_view(), name='grant_list'),

    # ========== RDP域名路由管理 ==========
    path('routes/', views_admin.AdminRouteListView.as_view(), name='route_list'),

    # ========== 系统任务管理 ==========
    path('tasks/', views_admin.AdminTaskListView.as_view(), name='task_list'),
]
