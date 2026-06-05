"""
Huey 任务包

导入所有任务模块，确保 Huey autodiscovery 能发现所有任务
"""

from app.tasks.bootstrap import (
    cleanup_expired_sessions,
    cleanup_expired_initial_tokens,
    generate_bootstrap_config,
    initialize_host_bootstrap,
    cert_provision_issue_certs,
    cleanup_expired_provision_tokens,
    cleanup_unactivated_certificates,
    cleanup_orphan_cert_dirs,
)

from app.tasks.operations import (
    process_opening_request,
    remote_set_admin,
    remote_remove_admin,
    remote_reset_windows_password,
    remote_set_disk_quota,
    remote_set_user_disk_quotas,
    remote_get_disk_info,
    execute_cloud_user_remote_action,
    process_account_creation,
    cleanup_expired_rdp_domains,
    allocate_rdp_domain,
    reset_user_password,
    batch_process_opening_requests,
    cleanup_inactive_users,
)

from app.tasks.hosts import (
    configure_winrm_on_host,
    test_winrm_connection,
    test_winrm_connection_raw,
    install_certificates_on_host,
)

from app.tasks.maintenance import (
    scheduled_cleanup_expired_sessions,
    scheduled_cleanup_expired_provision_tokens,
    scheduled_cleanup_unactivated_certificates,
    scheduled_cleanup_orphan_cert_dirs,
    scheduled_cleanup_expired_rdp_domains,
    scheduled_cleanup_expired_initial_tokens,
)

__all__ = [
    # Bootstrap tasks
    "cleanup_expired_sessions",
    "cleanup_expired_initial_tokens",
    "generate_bootstrap_config",
    "initialize_host_bootstrap",
    "cert_provision_issue_certs",
    "cleanup_expired_provision_tokens",
    "cleanup_unactivated_certificates",
    "cleanup_orphan_cert_dirs",
    # Operations tasks
    "process_opening_request",
    "remote_set_admin",
    "remote_remove_admin",
    "remote_reset_windows_password",
    "remote_set_disk_quota",
    "remote_set_user_disk_quotas",
    "remote_get_disk_info",
    "execute_cloud_user_remote_action",
    "process_account_creation",
    "cleanup_expired_rdp_domains",
    "allocate_rdp_domain",
    "reset_user_password",
    "batch_process_opening_requests",
    "cleanup_inactive_users",
    # Host tasks
    "configure_winrm_on_host",
    "test_winrm_connection",
    "test_winrm_connection_raw",
    "install_certificates_on_host",
    # Scheduled maintenance tasks
    "scheduled_cleanup_expired_sessions",
    "scheduled_cleanup_expired_provision_tokens",
    "scheduled_cleanup_unactivated_certificates",
    "scheduled_cleanup_orphan_cert_dirs",
    "scheduled_cleanup_expired_rdp_domains",
    "scheduled_cleanup_expired_initial_tokens",
]
