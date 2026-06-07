"""
操作记录URL配置
"""
from django.urls import path
from . import views

app_name = 'operations'

urlpatterns = [
    # 系统任务相关URL
    path('tasks/', views.SystemTaskListView.as_view(), name='task_list'),
    path('tasks/<int:pk>/', views.SystemTaskDetailView.as_view(), name='task_detail'),
    
    # 开户申请相关URL
    path('account-openings/', views.AccountOpeningRequestListView.as_view(), name='account_opening_list'),
    path('account-openings/create/', views.AccountOpeningRequestCreateView.as_view(), name='account_opening_create'),
    path('account-openings/confirm/', views.account_opening_confirm, name='account_opening_confirm'),
    path('account-openings/submit/', views.account_opening_submit, name='account_opening_submit'),
    # 已删除：approve/reject/process 路由 - 功能已迁移至 Django Admin
    path('account-openings/<int:pk>/', views.account_opening_detail, name='account_opening_detail'),
    
    # 云电脑用户相关URL
    path('cloud-users/', views.CloudComputerUserListView.as_view(), name='cloud_user_list'),
    # 已删除：toggle-status 路由 - 功能已迁移至 Django Admin
    
    # 我的云电脑相关URL
    path('my-cloud-computers/', views.MyCloudComputersView.as_view(), name='my_cloud_computers'),
    path('my-cloud-computers/<int:pk>/', views.my_cloud_computer_detail, name='my_cloud_computer_detail'),
    path('my-cloud-computers/<int:pk>/get-password/', views.get_password_and_burn, name='get_password_and_burn'),
    path('my-cloud-computers/<int:pk>/reset-password/', views.reset_password_and_burn, name='reset_password_and_burn'),

    # 磁盘配额相关API
    path('api/product/<int:product_id>/disk-config/', views.get_product_disk_config, name='product_disk_config'),
    path('api/host/<int:host_id>/disk-info/', views.get_host_disk_info, name='host_disk_info'),

    # 邀请链接相关URL
    path('invite/<str:token>/', views.product_invite_view, name='product_invite'),

    path('rdp/connect/<int:product_id>/', views.rdp_connect, name='rdp_connect'),
]