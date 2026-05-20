"""
超级管理员视图

用于超级管理员分配提供商给主机和主机组。
所有视图均使用 @superadmin_required 装饰器保护。
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator

from apps.accounts.provider_decorators import superadmin_required
from apps.accounts.forms_superadmin import (
    HostProviderAssignForm,
    HostGroupProviderAssignForm,
)
from apps.hosts.models import Host, HostGroup
from apps.hosts.views_admin import _get_permission_context


@superadmin_required
def superadmin_host_list(request):
    """
    超级管理员 - 主机列表视图

    显示所有主机及其已分配的提供商，支持搜索和筛选。
    """
    hosts = Host.objects.select_related('created_by').prefetch_related(
        'providers'
    ).order_by('-created_at')

    # 搜索
    search = request.GET.get('search', '').strip()
    if search:
        hosts = hosts.filter(
            name__icontains=search
        ) | hosts.filter(
            hostname__icontains=search
        )
        # 重新排序，因为 OR 查询会丢失排序
        hosts = hosts.order_by('-created_at')

    # 状态筛选
    status_filter = request.GET.get('status', '').strip()
    if status_filter:
        hosts = hosts.filter(status=status_filter)

    # 连接类型筛选
    connection_type_filter = request.GET.get('connection_type', '').strip()
    if connection_type_filter:
        hosts = hosts.filter(connection_type=connection_type_filter)

    # 分页
    paginator = Paginator(hosts, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'hosts': page_obj,
        'search': search,
        'status_filter': status_filter,
        'connection_type_filter': connection_type_filter,
        'status_choices': Host.STATUS_CHOICES,
        'connection_type_choices': Host.CONNECTION_TYPE_CHOICES,
        'active_nav': 'provider_hosts',
    }

    return render(request, 'admin_base/providers/host_list.html', context)


@superadmin_required
def superadmin_host_provider_assign(request, pk):
    """
    超级管理员 - 分配提供商给主机

    允许超级管理员为主机分配或移除提供商。
    """
    host = get_object_or_404(Host, pk=pk)

    if request.method == 'POST':
        form = HostProviderAssignForm(request.POST, host=host)
        if form.is_valid():
            providers = form.cleaned_data['providers']
            host.providers.set(providers)
            messages.success(
                request,
                f'已成功更新主机「{host.name}」的提供商分配，'
                f'当前分配 {providers.count()} 个提供商。'
            )
            return redirect('admin:admin_providers:provider_host_list')
    else:
        form = HostProviderAssignForm(host=host)

    context = {
        'host': host,
        'form': form,
        'current_providers': host.providers.all(),
        'active_nav': 'provider_hosts',
    }
    context.update(_get_permission_context(form, host))

    return render(
        request, 'admin_base/providers/host_provider_assign.html', context
    )


@superadmin_required
def superadmin_hostgroup_list(request):
    """
    超级管理员 - 主机组列表视图

    显示所有主机组及其已分配的提供商，支持搜索。
    """
    hostgroups = HostGroup.objects.select_related(
        'created_by'
    ).prefetch_related('providers', 'hosts').order_by('-created_at')

    # 搜索
    search = request.GET.get('search', '').strip()
    if search:
        hostgroups = hostgroups.filter(name__icontains=search)

    # 分页
    paginator = Paginator(hostgroups, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'hostgroups': page_obj,
        'search': search,
        'active_nav': 'provider_hosts',
    }

    return render(
        request, 'admin_base/providers/hostgroup_list.html', context
    )


@superadmin_required
def superadmin_hostgroup_provider_assign(request, pk):
    """
    超级管理员 - 分配提供商给主机组

    允许超级管理员为主机组分配或移除提供商。
    """
    hostgroup = get_object_or_404(HostGroup, pk=pk)

    if request.method == 'POST':
        form = HostGroupProviderAssignForm(request.POST, hostgroup=hostgroup)
        if form.is_valid():
            providers = form.cleaned_data['providers']
            hostgroup.providers.set(providers)
            messages.success(
                request,
                f'已成功更新主机组「{hostgroup.name}」的提供商分配，'
                f'当前分配 {providers.count()} 个提供商。'
            )
            return redirect('admin:admin_providers:provider_hostgroup_list')
    else:
        form = HostGroupProviderAssignForm(hostgroup=hostgroup)

    context = {
        'hostgroup': hostgroup,
        'form': form,
        'current_providers': hostgroup.providers.all(),
        'active_nav': 'provider_hosts',
    }

    return render(
        request,
        'admin_base/providers/hostgroup_provider_assign.html',
        context,
    )
