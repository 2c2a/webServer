"""
超管后台视图

包含超管仪表盘视图，所有视图均使用 @admin_required 装饰器保护。
超管可查看系统全局数据；站点组管理员可查看当前站点组数据；
提供商仅可查看自己相关的统计数据。
"""

from django.db.models import Q
from django.shortcuts import render
from django.contrib.auth import get_user_model

from apps.accounts.provider_decorators import admin_required
from utils.provider import get_provider_hosts, get_provider_products

User = get_user_model()


@admin_required
def admin_dashboard(request):
    """
    超管指挥中心视图

    渲染 admin_base/dashboard.html，传递任务导向的上下文数据。
    设计理念：不是数据库 CRUD 界面，而是智能指挥中心。
    """
    from apps.hosts.models import Host, HostGroup
    from apps.operations.models import (
        AccountOpeningRequest,
        CloudComputerUser,
        Product,
        ProductGroup,
        ProductInvitationToken,
        ProductAccessGrant,
        RdpDomainRoute,
    )
    from apps.tickets.models import Ticket, TicketCategory
    from apps.audit.models import AuditLog

    is_superuser = request.user.is_superuser
    site_group = getattr(request, "site_group", None)
    is_site_admin = (
        not is_superuser and site_group and request.user.is_site_group_admin(site_group)
    )

    provider_hosts = get_provider_hosts(request.user)
    provider_products = get_provider_products(request.user)

    # === 基础统计（数据隔离） ===
    if is_superuser:
        total_users = User.objects.count()
        total_hosts = Host.objects.count()
        total_hostgroups = HostGroup.objects.count()
        total_products = Product.objects.count()
        total_productgroups = ProductGroup.objects.count()
        pending_requests = AccountOpeningRequest.objects.filter(
            status="pending"
        ).count()
        total_cloud_users = CloudComputerUser.objects.filter(status="active").count()
        active_tokens = ProductInvitationToken.objects.filter(is_active=True).count()
        active_grants = ProductAccessGrant.objects.filter(is_revoked=False).count()
        open_tickets = Ticket.objects.filter(
            status__in=["pending", "processing", "waiting_feedback"]
        ).count()
        total_categories = TicketCategory.objects.count()
        total_routes = RdpDomainRoute.objects.count()
        total_audit_logs = AuditLog.objects.count()
    elif is_site_admin:
        sg = site_group
        total_users = (
            User.objects.filter(
                Q(provider_hosts__site_group=sg) | Q(created_products__site_group=sg)
            )
            .distinct()
            .count()
        )
        total_hosts = Host.objects.filter(site_group=sg).count()
        total_hostgroups = HostGroup.objects.filter(site_group=sg).count()
        total_products = Product.objects.filter(site_group=sg).count()
        total_productgroups = ProductGroup.objects.filter(site_group=sg).count()
        pending_requests = AccountOpeningRequest.objects.filter(
            status="pending",
            target_product__in=Product.objects.filter(site_group=sg),
        ).count()
        total_cloud_users = CloudComputerUser.objects.filter(
            status="active",
            product__in=Product.objects.filter(site_group=sg),
        ).count()
        active_tokens = ProductInvitationToken.objects.filter(
            is_active=True,
            product__in=Product.objects.filter(site_group=sg),
        ).count()
        active_grants = ProductAccessGrant.objects.filter(
            is_revoked=False,
            product__in=Product.objects.filter(site_group=sg),
        ).count()
        open_tickets = (
            Ticket.objects.filter(
                status__in=["pending", "processing", "waiting_feedback"],
            )
            .filter(Q(related_product__site_group=sg) | Q(related_host__site_group=sg))
            .count()
        )
        total_categories = TicketCategory.objects.count()
        total_routes = RdpDomainRoute.objects.filter(
            product__in=Product.objects.filter(site_group=sg),
        ).count()
        total_audit_logs = AuditLog.objects.filter(
            Q(host__site_group=sg) | Q(host__isnull=True)
        ).count()
    else:
        total_users = (
            User.objects.filter(
                Q(cloud_users__product__in=provider_products)
                | Q(provider_hosts__in=provider_hosts)
            )
            .distinct()
            .count()
        )
        total_hosts = provider_hosts.count()
        total_hostgroups = HostGroup.objects.filter(created_by=request.user).count()
        total_products = provider_products.count()
        total_productgroups = ProductGroup.objects.filter(
            created_by=request.user
        ).count()
        pending_requests = AccountOpeningRequest.objects.filter(
            status="pending",
            target_product__in=provider_products,
        ).count()
        total_cloud_users = CloudComputerUser.objects.filter(
            status="active",
            product__in=provider_products,
        ).count()
        active_tokens = ProductInvitationToken.objects.filter(
            is_active=True,
            created_by=request.user,
        ).count()
        active_grants = ProductAccessGrant.objects.filter(
            is_revoked=False,
            product__in=provider_products,
        ).count()
        open_tickets = Ticket.objects.filter(
            status__in=["pending", "processing", "waiting_feedback"],
            related_product__in=provider_products,
        ).count()
        total_categories = TicketCategory.objects.filter(
            created_by=request.user
        ).count()
        total_routes = RdpDomainRoute.objects.filter(
            product__in=provider_products,
        ).count()
        total_audit_logs = AuditLog.objects.filter(host__in=provider_hosts).count()

    # === 需要关注的事项 ===
    if is_superuser:
        hosts_without_providers = Host.objects.filter(providers__isnull=True).count()
        offline_hosts = Host.objects.filter(status="offline").count()
    elif is_site_admin:
        sg = site_group
        sg_hosts = Host.objects.filter(site_group=sg)
        hosts_without_providers = sg_hosts.filter(providers__isnull=True).count()
        offline_hosts = sg_hosts.filter(status="offline").count()
    else:
        hosts_without_providers = provider_hosts.filter(providers__isnull=True).count()
        offline_hosts = provider_hosts.filter(status="offline").count()

    attention_items = []
    if hosts_without_providers > 0:
        attention_items.append(
            {
                "icon": "dns",
                "description": f"{hosts_without_providers} 台主机未分配提供商",
                "action_label": "分配",
                "action_url": "admin:admin_providers:provider_host_list",
                "severity": "warning",
            }
        )
    if pending_requests > 0:
        attention_items.append(
            {
                "icon": "person_add",
                "description": f"{pending_requests} 条开户申请待审批",
                "action_label": "审批",
                "action_url": "admin:admin_operations:request_list",
                "severity": "warning",
            }
        )
    if open_tickets > 0:
        attention_items.append(
            {
                "icon": "confirmation_number",
                "description": f"{open_tickets} 个工单待处理",
                "action_label": "处理",
                "action_url": "admin:admin_tickets:ticket_list",
                "severity": "warning",
            }
        )
    if offline_hosts > 0:
        attention_items.append(
            {
                "icon": "cloud_off",
                "description": f"{offline_hosts} 台主机离线",
                "action_label": "查看",
                "action_url": "admin:admin_hosts:host_list",
                "severity": "error",
            }
        )

    # === 快捷操作 ===
    quick_actions = [
        {
            "label": "添加主机",
            "icon": "dns",
            "url": "admin:admin_hosts:host_create",
            "variant": "filled",
        },
        {
            "label": "入驻提供商",
            "icon": "person_add",
            "url": "admin:admin_users:user_create",
            "variant": "filled",
        },
        {
            "label": "审批申请",
            "icon": "how_to_reg",
            "url": "admin:admin_operations:request_list",
            "variant": "filled",
            "badge": pending_requests if pending_requests > 0 else None,
        },
        {
            "label": "查看工单",
            "icon": "confirmation_number",
            "url": "admin:admin_tickets:ticket_list",
            "variant": "filled",
            "badge": open_tickets if open_tickets > 0 else None,
        },
    ]

    # === 系统健康状态 ===
    if is_superuser:
        online_hosts = Host.objects.filter(status="online").count()
        active_tunnels = Host.objects.filter(tunnel_status="online").count()
        inactive_tunnels = (
            Host.objects.exclude(tunnel_status="no_tunnel")
            .exclude(tunnel_status="online")
            .count()
        )
    elif is_site_admin:
        sg = site_group
        sg_hosts = Host.objects.filter(site_group=sg)
        online_hosts = sg_hosts.filter(status="online").count()
        active_tunnels = sg_hosts.filter(tunnel_status="online").count()
        inactive_tunnels = (
            sg_hosts.exclude(tunnel_status="no_tunnel")
            .exclude(tunnel_status="online")
            .count()
        )
    else:
        online_hosts = provider_hosts.filter(status="online").count()
        active_tunnels = provider_hosts.filter(tunnel_status="online").count()
        inactive_tunnels = (
            provider_hosts.exclude(tunnel_status="no_tunnel")
            .exclude(tunnel_status="online")
            .count()
        )

    system_health = {
        "online_hosts": online_hosts,
        "offline_hosts": offline_hosts,
        "total_hosts": total_hosts,
        "active_tunnels": active_tunnels,
        "inactive_tunnels": inactive_tunnels,
        "active_users": total_cloud_users,
        "active_products": total_products,
    }

    # === 最近动态 ===
    if is_superuser:
        recent_logs = AuditLog.objects.select_related("user", "host").order_by(
            "-timestamp"
        )[:10]
    elif is_site_admin:
        sg = site_group
        recent_logs = (
            AuditLog.objects.filter(Q(host__site_group=sg) | Q(host__isnull=True))
            .select_related("user", "host")
            .order_by("-timestamp")[:10]
        )
    else:
        recent_logs = (
            AuditLog.objects.filter(host__in=provider_hosts)
            .select_related("user", "host")
            .order_by("-timestamp")[:10]
        )

    # 为审计日志构建可读描述
    action_display_map = dict(AuditLog.ACTION_CHOICES)
    recent_activities = []
    for log in recent_logs:
        action_text = action_display_map.get(log.action, log.action)
        description = action_text
        if log.host:
            description = f"{action_text} - {log.host.name}"
        recent_activities.append(
            {
                "timestamp": log.timestamp,
                "icon": _get_action_icon(log.action),
                "description": description,
                "actor": log.user.username if log.user else "系统",
                "success": log.success,
            }
        )

    context = {
        "stats": {
            "total_users": total_users,
            "total_hosts": total_hosts,
            "total_hostgroups": total_hostgroups,
            "total_products": total_products,
            "total_productgroups": total_productgroups,
            "pending_requests": pending_requests,
            "total_cloud_users": total_cloud_users,
            "active_tokens": active_tokens,
            "active_grants": active_grants,
            "open_tickets": open_tickets,
            "total_categories": total_categories,
            "total_routes": total_routes,
            "total_audit_logs": total_audit_logs,
        },
        "attention_items": attention_items,
        "quick_actions": quick_actions,
        "recent_activities": recent_activities,
        "system_health": system_health,
        "page_title": "超管指挥中心",
        "active_nav": "dashboard",
    }

    return render(request, "admin_base/dashboard.html", context)


def _get_action_icon(action):
    """根据审计操作类型返回对应的 Material Icon 名称"""
    icon_map = {
        "create_user": "person_add",
        "delete_user": "person_remove",
        "reset_password": "key",
        "connect_host": "lan",
        "modify_host": "edit",
        "view_password": "visibility",
        "approve_request": "check_circle",
        "reject_request": "cancel",
        "bootstrap_host": "rocket_launch",
        "issue_cert": "verified",
        "revoke_cert": "gpp_bad",
        "create_host": "add_circle",
        "delete_host": "remove_circle",
        "update_host": "update",
        "process_opening_request": "how_to_reg",
        "batch_process_requests": "playlist_add_check",
        "login": "login",
        "logout": "logout",
        "view_audit_log": "receipt_long",
        "admin_action": "admin_panel_settings",
        "tunnel_online": "link",
        "tunnel_offline": "link_off",
        "tunnel_heartbeat_timeout": "heart_broken",
        "rdp_connect": "desktop_windows",
        "rdp_disconnect": "desktop_access_disabled",
        "remote_exec": "terminal",
        "remote_exec_result": "terminal",
        "domain_bind": "language",
        "domain_unbind": "language",
        "create_ticket": "add_task",
        "update_ticket": "edit_note",
        "assign_ticket": "assignment_ind",
        "change_ticket_status": "swap_horiz",
        "close_ticket": "task_alt",
        "add_ticket_comment": "comment",
    }
    return icon_map.get(action, "circle")
