from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.accounts.provider_decorators import superadmin_required
from .models import SiteGroup, SiteGroupHostname
from .forms_sitegroup import SiteGroupForm, SiteGroupHostnameForm


@superadmin_required
def sitegroup_list(request):
    sitegroups = SiteGroup.objects.all()
    return render(request, 'dashboard/sitegroup_list.html', {
        'sitegroups': sitegroups,
        'active_nav': 'sitegroups',
    })


@superadmin_required
def sitegroup_create(request):
    if request.method == 'POST':
        form = SiteGroupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, '站点组创建成功')
            return redirect('dashboard:sitegroup_list')
    else:
        form = SiteGroupForm()
    return render(request, 'dashboard/sitegroup_form.html', {
        'form': form,
        'title': '创建站点组',
        'active_nav': 'sitegroups',
    })


@superadmin_required
def sitegroup_update(request, pk):
    sitegroup = get_object_or_404(SiteGroup, pk=pk)
    if request.method == 'POST':
        form = SiteGroupForm(request.POST, instance=sitegroup)
        if form.is_valid():
            form.save()
            messages.success(request, '站点组更新成功')
            return redirect('dashboard:sitegroup_list')
    else:
        form = SiteGroupForm(instance=sitegroup)
    return render(request, 'dashboard/sitegroup_form.html', {
        'form': form,
        'title': '编辑站点组',
        'sitegroup': sitegroup,
        'active_nav': 'sitegroups',
    })


@superadmin_required
def sitegroup_delete(request, pk):
    sitegroup = get_object_or_404(SiteGroup, pk=pk)
    if request.method == 'POST':
        sitegroup.delete()
        messages.success(request, '站点组已删除')
        return redirect('dashboard:sitegroup_list')
    return render(request, 'dashboard/sitegroup_detail.html', {
        'sitegroup': sitegroup,
        'active_nav': 'sitegroups',
    })


@superadmin_required
def sitegroup_detail(request, pk):
    sitegroup = get_object_or_404(SiteGroup, pk=pk)
    hostnames = sitegroup.hostnames.all()
    admins = sitegroup.admins.all()
    return render(request, 'dashboard/sitegroup_detail.html', {
        'sitegroup': sitegroup,
        'hostnames': hostnames,
        'admins': admins,
        'active_nav': 'sitegroups',
    })


@superadmin_required
def sitegroup_add_hostname(request, pk):
    sitegroup = get_object_or_404(SiteGroup, pk=pk)
    if request.method == 'POST':
        form = SiteGroupHostnameForm(request.POST)
        if form.is_valid():
            hostname = form.save(commit=False)
            hostname.site_group = sitegroup
            hostname.save()
            messages.success(request, f'主机名 {hostname.hostname} 已绑定')
        else:
            for error in form.errors.get_json_data().values():
                for e in error:
                    messages.error(request, e['message'])
    return redirect('dashboard:sitegroup_detail', pk=pk)


@superadmin_required
def sitegroup_remove_hostname(request, pk, hostname_pk):
    sitegroup = get_object_or_404(SiteGroup, pk=pk)
    hostname = get_object_or_404(SiteGroupHostname, pk=hostname_pk, site_group=sitegroup)
    if request.method == 'POST':
        hostname.delete()
        messages.success(request, f'主机名 {hostname.hostname} 已解绑')
    return redirect('dashboard:sitegroup_detail', pk=pk)


@superadmin_required
def sitegroup_add_admin(request, pk):
    sitegroup = get_object_or_404(SiteGroup, pk=pk)
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        if username:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(username=username)
                if user.is_superuser:
                    messages.warning(request, f'用户 {username} 已是超级管理员，无需添加')
                elif sitegroup.admins.filter(pk=user.pk).exists():
                    messages.warning(request, f'用户 {username} 已是该站点组管理员')
                else:
                    sitegroup.admins.add(user)
                    messages.success(request, f'已将 {username} 添加为站点组管理员')
            except User.DoesNotExist:
                messages.error(request, f'用户 {username} 不存在')
    return redirect('dashboard:sitegroup_detail', pk=pk)


@superadmin_required
def sitegroup_remove_admin(request, pk, user_pk):
    sitegroup = get_object_or_404(SiteGroup, pk=pk)
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = get_object_or_404(User, pk=user_pk)
    if request.method == 'POST':
        sitegroup.admins.remove(user)
        messages.success(request, f'已移除 {user.username} 的站点组管理员权限')
    return redirect('dashboard:sitegroup_detail', pk=pk)
