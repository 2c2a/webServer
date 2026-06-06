from django.urls import path

from .views_admin import (
    widget_list,
    widget_create,
    widget_edit,
    widget_delete,
    systemconfig_edit,
    systemconfig_send_test_email,
    test_email_progress,
    test_email_sse,
)

app_name = 'admin_dashboard_config'

urlpatterns = [
    path('widgets/', widget_list, name='widget_list'),
    path('widgets/create/', widget_create, name='widget_create'),
    path('widgets/<int:pk>/edit/', widget_edit, name='widget_edit'),
    path('widgets/<int:pk>/delete/', widget_delete, name='widget_delete'),
    path('config/', systemconfig_edit, name='systemconfig_edit'),
    path(
        'config/send-test-email/',
        systemconfig_send_test_email,
        name='systemconfig_send_test_email',
    ),
    path(
        'config/test-email/<int:task_pk>/',
        test_email_progress,
        name='test_email_progress',
    ),
    path(
        'config/test-email/<int:task_pk>/sse/',
        test_email_sse,
        name='test_email_sse',
    ),
]
