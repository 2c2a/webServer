from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from apps.accounts.provider_decorators import superadmin_required
from apps.accounts.models import RegistrationLink


@superadmin_required
def reglink_list(request):
    queryset = RegistrationLink.objects.select_related(
        'group', 'created_by', 'used_by'
    ).order_by('-created_at')

    status_filter = request.GET.get('status', '').strip()
    if status_filter == 'unused':
        queryset = queryset.filter(used=False)
    elif status_filter == 'used':
        queryset = queryset.filter(used=True)
    elif status_filter == 'expired':
        queryset = queryset.filter(used=False, expires_at__lt=timezone.now())

    group_filter = request.GET.get('group', '').strip()
    if group_filter:
        queryset = queryset.filter(group_id=group_filter)

    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(note__icontains=search) | Q(token__icontains=search)
        )

    all_groups = Group.objects.select_related('profile').order_by('name')

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'all_groups': all_groups,
        'status_filter': status_filter,
        'group_filter': group_filter,
        'search': search,
        'active_nav': 'reglinks',
    }
    return render(request, 'admin_base/reglinks/reglink_list.html', context)


@superadmin_required
def reglink_create(request):
    all_groups = Group.objects.select_related('profile').order_by('name')

    if request.method == 'POST':
        group_id = request.POST.get('group', '').strip()
        expires_at_str = request.POST.get('expires_at', '').strip()
        max_uses_str = request.POST.get('max_uses', '').strip()
        note = request.POST.get('note', '').strip()

        if not group_id:
            messages.error(request, '请选择注册后的用户组')
            context = {
                'all_groups': all_groups,
                'active_nav': 'reglinks',
            }
            return render(request, 'admin_base/reglinks/reglink_form.html', context)

        try:
            group = Group.objects.get(pk=group_id)
        except Group.DoesNotExist:
            messages.error(request, '所选用户组不存在')
            context = {
                'all_groups': all_groups,
                'active_nav': 'reglinks',
            }
            return render(request, 'admin_base/reglinks/reglink_form.html', context)

        max_uses = 1
        if max_uses_str:
            try:
                max_uses = int(max_uses_str)
                if max_uses < 0:
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, '最大使用次数必须为非负整数')
                context = {
                    'all_groups': all_groups,
                    'active_nav': 'reglinks',
                }
                return render(
                    request, 'admin_base/reglinks/reglink_form.html', context
                )

        expires_at = None
        if expires_at_str:
            try:
                expires_at = timezone.datetime.fromisoformat(expires_at_str)
                if timezone.is_naive(expires_at):
                    expires_at = timezone.make_aware(expires_at)
            except (ValueError, TypeError):
                messages.error(request, '过期时间格式不正确')
                context = {
                    'all_groups': all_groups,
                    'active_nav': 'reglinks',
                }
                return render(
                    request, 'admin_base/reglinks/reglink_form.html', context
                )

        reglink = RegistrationLink.objects.create(
            group=group,
            created_by=request.user,
            max_uses=max_uses,
            expires_at=expires_at,
            note=note,
        )

        messages.success(request, f'注册链接创建成功，用户将加入「{group.name}」组')
        return redirect('admin:admin_reglinks:reglink_list')

    context = {
        'all_groups': all_groups,
        'active_nav': 'reglinks',
    }
    return render(request, 'admin_base/reglinks/reglink_form.html', context)


@superadmin_required
def reglink_delete(request, pk):
    reglink = get_object_or_404(RegistrationLink, pk=pk)

    if reglink.is_exhausted:
        messages.error(request, '已用完的注册链接不可删除')
        return redirect('admin:admin_reglinks:reglink_list')

    if request.method == 'POST':
        reglink.delete()
        messages.success(request, '注册链接已删除')
        return redirect('admin:admin_reglinks:reglink_list')

    context = {
        'reglink': reglink,
        'active_nav': 'reglinks',
    }
    return render(request, 'admin_base/reglinks/reglink_confirm_delete.html', context)


@superadmin_required
def reglink_copy_url(request, pk):
    reglink = get_object_or_404(RegistrationLink, pk=pk)
    from django.urls import reverse
    url = request.build_absolute_uri(
        reverse('accounts:register_by_link', kwargs={'token': reglink.token})
    )
    return {'url': url}
