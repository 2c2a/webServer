"""
站点组管理员 - 用户管理视图

站点组管理员只能管理本站点组内的用户。
支持：用户列表、封禁/解封、重置密码。
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q

from apps.accounts.provider_decorators import site_group_admin_required
from apps.accounts.forms_admin import AdminPasswordResetForm
from apps.accounts.models import UserBan
from apps.accounts.user_service import ban_user, unban_user

User = get_user_model()


@site_group_admin_required
def sitegroup_user_list(request):
    """站点组用户列表"""
    site_group = request.site_group
    if not site_group:
        messages.error(request, "未识别到站点组")
        return redirect("dashboard:index")

    queryset = (
        User.objects.filter(site_groups=site_group)
        .prefetch_related("groups")
        .select_related("active_ban")
        .order_by("-created_at")
    )

    search = request.GET.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(username__icontains=search)
            | Q(email__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )

    active_filter = request.GET.get("is_active", "").strip()
    if active_filter == "1":
        queryset = queryset.filter(is_active=True)
    elif active_filter == "0":
        queryset = queryset.filter(is_active=False)

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    admin_ids = set(site_group.admins.values_list("pk", flat=True))

    context = {
        "site_group": site_group,
        "admin_ids": admin_ids,
        "page_obj": page_obj,
        "search": search,
        "active_filter": active_filter,
        "active_nav": "sitegroup_users",
    }
    return render(request, "dashboard/sitegroup_user_list.html", context)


@site_group_admin_required
def sitegroup_user_toggle_active(request, user_pk):
    """站点组管理员封禁/解封用户"""
    site_group = request.site_group
    if not site_group:
        messages.error(request, "未识别到站点组")
        return redirect("dashboard:index")

    user = get_object_or_404(
        User, pk=user_pk, site_groups=site_group
    )

    # 不能封禁自己
    if user.pk == request.user.pk:
        messages.error(request, "不能封禁自己的账号")
        return redirect("dashboard:sitegroup_user_list")

    # 不能封禁超管
    if user.is_superuser:
        messages.error(request, "不能封禁超级管理员")
        return redirect("dashboard:sitegroup_user_list")

    if request.method == "POST":
        is_banned = UserBan.objects.filter(user=user).exists()
        if is_banned:
            # 解封
            unban_user(user, unbanned_by=request.user)
            status_text = "解封"
        else:
            # 封禁
            reason = request.POST.get("ban_reason", "").strip()
            if not reason:
                reason = f"站点组 {site_group.name} 管理员封禁"
            ban_user(user, reason=reason, banned_by=request.user)
            status_text = "封禁"

        messages.success(
            request, f"用户「{user.username}」已{status_text}"
        )

    return redirect("dashboard:sitegroup_user_list")


@site_group_admin_required
def sitegroup_user_reset_password(request, user_pk):
    """站点组管理员重置用户密码"""
    site_group = request.site_group
    if not site_group:
        messages.error(request, "未识别到站点组")
        return redirect("dashboard:index")

    user = get_object_or_404(
        User, pk=user_pk, site_groups=site_group
    )

    if user.is_superuser:
        messages.error(request, "不能重置超级管理员密码")
        return redirect("dashboard:sitegroup_user_list")

    if request.method == "POST":
        form = AdminPasswordResetForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data["new_password1"])
            user.save()
            messages.success(
                request, f"用户「{user.username}」密码已重置"
            )
            return redirect("dashboard:sitegroup_user_list")
    else:
        form = AdminPasswordResetForm()

    context = {
        "site_group": site_group,
        "form": form,
        "target_user": user,
        "active_nav": "sitegroup_users",
    }
    return render(
        request, "dashboard/sitegroup_user_reset_password.html", context
    )


@site_group_admin_required
def sitegroup_user_remove(request, user_pk):
    """站点组管理员将用户移出本站点组"""
    site_group = request.site_group
    if not site_group:
        messages.error(request, "未识别到站点组")
        return redirect("dashboard:index")

    user = get_object_or_404(
        User, pk=user_pk, site_groups=site_group
    )

    if user.is_superuser:
        messages.error(request, "不能移出超级管理员")
        return redirect("dashboard:sitegroup_user_list")

    if request.method == "POST":
        user.site_groups.remove(site_group)
        messages.success(
            request,
            f"用户「{user.username}」已从站点组「{site_group.name}」移出",
        )
        return redirect("dashboard:sitegroup_user_list")

    context = {
        "site_group": site_group,
        "target_user": user,
        "active_nav": "sitegroup_users",
    }
    return render(
        request, "dashboard/sitegroup_user_remove.html", context
    )
