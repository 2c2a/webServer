from django.urls import path
from . import views

app_name = 'bootstrap'

urlpatterns = [
    # 引导配置API
    path('config/', views.get_bootstrap_config, name='get_bootstrap_config'),
    path('trigger/', views.trigger_host_bootstrap, name='trigger_host_bootstrap'),
    path('create-initial-token/', views.create_initial_token, name='create_initial_token'),
    path('status/', views.check_bootstrap_status, name='check_bootstrap_status'),
    path('validate-token/', views.validate_bootstrap_token, name='validate_bootstrap_token'),
    
    # 引导管理API
    path('manage/', views.BootstrapManagementView.as_view(), name='bootstrap_management'),
    
    # 新增API端点 - 基于配对码的认证机制
    path('verify-pairing-code/', views.verify_pairing_code, name='verify_pairing_code'),
    path('api/verify-pairing-code/', views.verify_pairing_code, name='api_verify_pairing_code'),
    path('exchange-token/', views.exchange_token, name='exchange_token'),
    path('session/', views.revoke_session, name='revoke_session'),
    
    # API端点别名 - 为H端提供兼容路径
    path('api/verify_pairing_code/', views.verify_pairing_code, name='api_verify_pairing_code'),
    path('api/exchange_token/', views.exchange_token, name='api_exchange_token'),
    path('api/get_session_token', views.get_session_token, name='api_get_session_token_no_slash'),  # 不带斜杠版本
    path('api/get_session_token/', views.get_session_token, name='api_get_session_token'),
    path('api/upload_host_cert/', views.upload_host_cert, name='api_upload_host_cert'),
    path('api/check_pairing_status', views.check_pairing_status, name='api_check_pairing_status'),  # 新增：检查配对状态
    path('api/session/', views.revoke_session, name='api_revoke_session'),
    
    # 自动注册API
    path('api/auto-register/', views.auto_register_host, name='auto_register_host'),
    path('api/complete-auto-register/', views.complete_auto_register, name='complete_auto_register'),
    path('api/pending-hosts/', views.get_pending_hosts, name='get_pending_hosts'),
    path('api/revoke-pending-host/', views.revoke_pending_host, name='revoke_pending_host'),

    path('sse/init-status/', views.sse_init_status, name='sse_init_status'),

    path('api/cert-provision/validate/', views.cert_provision_validate, name='cert_provision_validate'),
    path('api/cert-provision/upload-hostname/', views.cert_provision_upload_hostname, name='cert_provision_upload_hostname'),
    path('api/cert-provision/download-certs/', views.cert_provision_download_certs, name='cert_provision_download_certs'),
    path('api/cert-provision/notify-complete/', views.cert_provision_notify_complete, name='cert_provision_notify_complete'),
    path('api/cert-provision/disable-password-auth/', views.cert_provision_disable_password_auth, name='cert_provision_disable_password_auth'),
    path('api/cert-provision/test-result/', views.cert_provision_test_result, name='cert_provision_test_result'),
    path('api/cert-provision/status-stream/', views.cert_provision_status_stream, name='cert_provision_status_stream'),
    path('api/cert-provision/test-stream/', views.cert_provision_test_stream, name='cert_provision_test_stream'),
]