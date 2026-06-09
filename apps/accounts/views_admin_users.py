"""
超管后台 - 用户管理视图

所有视图均使用 @superadmin_required 装饰器保护。
超管后台无数据隔离，可查看系统全局数据。
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.provider_decorators import superadmin_required
from apps.accounts.models import UserBan
from apps.accounts.user_service import ban_user, unban_user
from .forms_admin import (
    AdminUserCreateForm,
    AdminUserUpdateForm,
    AdminPasswordResetForm,
)

User = get_user_model()


@superadmin_required
def user_list(request):
    """
    用户列表视图

    支持按用户名/邮箱/姓名搜索，按 is_staff/is_active 筛选。
    显示用户组信息，分页展示。
    """
    queryset = User.objects.prefetch_related(
        'groups'
    ).select_related('active_ban').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    staff_filter = request.GET.get('is_staff', '').strip()
    if staff_filter == '1':
        queryset = queryset.filter(is_staff=True)
    elif staff_filter == '0':
        queryset = queryset.filter(is_staff=False)

    active_filter = request.GET.get('is_active', '').strip()
    if active_filter == '1':
        queryset = queryset.filter(is_active=True)
    elif active_filter == '0':
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'staff_filter': staff_filter,
        'active_filter': active_filter,
        'active_nav': 'users',
    }

    return render(request, 'admin_base/users/user_list.html', context)


@superadmin_required
def user_create(request):
    """创建用户视图"""
    if request.method == 'POST':
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'用户「{user.username}」创建成功')
            return redirect('admin:admin_users:user_list')
    else:
        form = AdminUserCreateForm()

    context = {
        'form': form,
        'is_create': True,
        'active_nav': 'users',
    }

    return render(request, 'admin_base/users/user_form.html', context)


@superadmin_required
def user_update(request, pk):
    """编辑用户视图"""
    user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = AdminUserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(
                request, f'用户「{user.username}」更新成功'
            )
            return redirect('admin:admin_users:user_list')
    else:
        form = AdminUserUpdateForm(instance=user)

    context = {
        'form': form,
        'target_user': user,
        'is_create': False,
        'active_nav': 'users',
    }

    return render(request, 'admin_base/users/user_form.html', context)


@superadmin_required
def user_delete(request, pk):
    """删除用户视图（含自删除保护）"""
    user = get_object_or_404(User, pk=pk)

    if user.pk == request.user.pk:
        messages.error(request, '不能删除自己的账号')
        return redirect('admin:admin_users:user_list')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'用户「{username}」已删除')
        return redirect('admin:admin_users:user_list')

    context = {
        'target_user': user,
        'active_nav': 'users',
    }

    return render(
        request, 'admin_base/users/user_confirm_delete.html', context
    )


@superadmin_required
def user_toggle_active(request, pk):
    """切换用户封禁状态（POST 操作，完成后重定向回列表）"""
    user = get_object_or_404(User, pk=pk)

    if user.pk == request.user.pk:
        messages.error(request, '不能封禁自己的账号')
        return redirect('admin:admin_users:user_list')

    if request.method == 'POST':
        is_banned = UserBan.objects.filter(user=user).exists()
        if is_banned:
            # 解封
            unban_user(user, unbanned_by=request.user)
            messages.success(request, f'用户「{user.username}」已解封')
        else:
            # 封禁
            reason = request.POST.get('ban_reason', '').strip()
            ban_user(user, reason=reason, banned_by=request.user)
            messages.success(request, f'用户「{user.username}」已封禁')

    return redirect('admin:admin_users:user_list')


@superadmin_required
def user_reset_password(request, pk):
    """重置用户密码视图"""
    user = get_object_or_404(User, pk=pk)

    if request.method == 'POST':
        form = AdminPasswordResetForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data['new_password1'])
            user.save()
            messages.success(
                request, f'用户「{user.username}」密码已重置'
            )
            return redirect('admin:admin_users:user_list')
    else:
        form = AdminPasswordResetForm()

    context = {
        'form': form,
        'target_user': user,
        'active_nav': 'users',
    }

    return render(
        request, 'admin_base/users/user_reset_password.html', context
    )
