"""
工单系统 - 超管后台视图

超管可查看所有数据；提供商仅可查看自己创建的分类及关联的工单。
包含：
- AdminTicketListView: 所有工单列表，搜索、筛选、批量操作
- AdminTicketDetailView: 工单详情，含评论和附件
- AdminTicketCommentCreateView: 添加评论 (POST)
- AdminCategoryListView: 所有分类列表
- AdminCategoryCreateView: 创建分类
- AdminCategoryUpdateView: 编辑分类
- AdminCategoryDeleteView: 删除分类
- AdminActivityListView: 所有活动记录（只读）
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from apps.accounts.provider_decorators import admin_required
from utils.provider import get_provider_products

from .forms_admin import AdminTicketCategoryForm, AdminTicketCommentForm
from .models import (
    Ticket,
    TicketActivity,
    TicketCategory,
    TicketComment,
)

User = get_user_model()


def _ticket_filter_for_user(user, site_group):
    if user.is_superuser:
        return Q()
    if site_group and user.is_site_group_admin(site_group):
        return (
            Q(related_product__site_group=site_group)
            | Q(related_host__site_group=site_group)
            | Q(creator=user)
        )
    provider_products = get_provider_products(user)
    return Q(related_product__in=provider_products) | Q(creator=user)


def _category_filter_for_user(user, site_group):
    if user.is_superuser:
        return Q()
    if site_group and user.is_site_group_admin(site_group):
        return Q()
    return Q(created_by=user)


# ===========================================================================
# 工单管理
# ===========================================================================


@admin_required
def admin_ticket_list(request):
    """
    超管工单列表视图

    - 无数据隔离，查看所有工单
    - 支持状态筛选、优先级筛选、搜索、批量操作
    """
    queryset = Ticket.objects.select_related(
        "category",
        "creator",
        "assignee",
        "assigned_group",
        "related_product",
        "related_host",
    )

    site_group = getattr(request, "site_group", None)
    ticket_filter = _ticket_filter_for_user(request.user, site_group)
    if ticket_filter:
        queryset = queryset.filter(ticket_filter).distinct()

    # 状态筛选
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # 优先级筛选
    priority_filter = request.GET.get("priority", "").strip()
    if priority_filter:
        queryset = queryset.filter(priority=priority_filter)

    # 搜索
    search = request.GET.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(ticket_no__icontains=search)
            | Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(creator__username__icontains=search)
        )

    # 排序
    queryset = queryset.order_by("-created_at")

    # 分页
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # 统计各状态数量
    if request.user.is_superuser:
        base_qs = Ticket.objects.all()
    else:
        base_qs = Ticket.objects.filter(ticket_filter).distinct()
    status_counts = {
        "pending": base_qs.filter(status="pending").count(),
        "processing": base_qs.filter(status="processing").count(),
        "waiting_feedback": base_qs.filter(status="waiting_feedback").count(),
        "resolved": base_qs.filter(status="resolved").count(),
        "closed": base_qs.filter(status="closed").count(),
        "rejected": base_qs.filter(status="rejected").count(),
    }

    context = {
        "page_obj": page_obj,
        "tickets": page_obj,
        "search": search,
        "status_filter": status_filter,
        "priority_filter": priority_filter,
        "status_counts": status_counts,
        "status_choices": Ticket.STATUS_CHOICES,
        "priority_choices": Ticket.PRIORITY_CHOICES,
        "page_title": "工单管理",
        "active_nav": "admin_tickets",
    }

    return render(request, "admin_base/tickets/ticket_list.html", context)


@admin_required
def admin_ticket_detail(request, pk):
    """
    超管工单详情视图

    显示工单信息、评论列表（含内部备注）、附件列表、活动记录。
    """
    site_group = getattr(request, "site_group", None)
    ticket_filter = _ticket_filter_for_user(request.user, site_group)
    if ticket_filter:
        ticket = get_object_or_404(
            Ticket.objects.select_related(
                "category",
                "creator",
                "assignee",
                "assigned_group",
                "related_product",
                "related_host",
            ).filter(ticket_filter),
            pk=pk,
        )
    else:
        ticket = get_object_or_404(
            Ticket.objects.select_related(
                "category",
                "creator",
                "assignee",
                "assigned_group",
                "related_product",
                "related_host",
            ),
            pk=pk,
        )

    # 评论列表（超管可见内部备注）
    comments = ticket.comments.select_related("author").order_by("created_at")

    # 附件列表
    attachments = ticket.attachments.select_related("uploaded_by").order_by(
        "-created_at"
    )

    # 活动记录
    activities = ticket.activities.select_related("actor").order_by("-created_at")[:10]

    context = {
        "ticket": ticket,
        "comments": comments,
        "attachments": attachments,
        "activities": activities,
        "comment_form": AdminTicketCommentForm(),
        "page_title": f"工单 {ticket.ticket_no}",
        "active_nav": "admin_tickets",
    }

    return render(request, "admin_base/tickets/ticket_detail.html", context)


@admin_required
@require_POST
def admin_ticket_comment_create(request, pk):
    """
    超管添加工单评论 (POST)

    超管添加的评论自动标记作者为当前用户。
    """
    site_group = getattr(request, "site_group", None)
    ticket_filter = _ticket_filter_for_user(request.user, site_group)
    if ticket_filter:
        ticket = get_object_or_404(
            Ticket.objects.filter(ticket_filter),
            pk=pk,
        )
    else:
        ticket = get_object_or_404(Ticket, pk=pk)

    form = AdminTicketCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.ticket = ticket
        comment.author = request.user
        comment.save()

        messages.success(request, "评论已添加。")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, error)

    return redirect("admin:admin_tickets:ticket_detail", pk=ticket.pk)


# ===========================================================================
# 工单批量操作
# ===========================================================================


def _get_selected_ids(request):
    """从 POST 请求中获取选中的工单 ID 列表"""
    selected = request.POST.getlist("selected_ids")
    return [int(pk) for pk in selected if pk.isdigit()]


@admin_required
@require_POST
def admin_ticket_batch_processing(request):
    """批量标记工单为处理中"""
    selected_ids = _get_selected_ids(request)
    if not selected_ids:
        messages.warning(request, "未选择任何工单。")
        return redirect("admin:admin_tickets:ticket_list")

    qs = Ticket.objects.filter(
        pk__in=selected_ids,
        status="pending",
    )
    site_group = getattr(request, "site_group", None)
    ticket_filter = _ticket_filter_for_user(request.user, site_group)
    if ticket_filter:
        qs = qs.filter(ticket_filter).distinct()

    updated_count = 0
    for ticket in qs:
        ticket.status = "processing"
        ticket.assignee = request.user
        ticket._current_user = request.user
        ticket.save(update_fields=["status", "assignee", "updated_at"])
        updated_count += 1

    if updated_count > 0:
        messages.success(
            request,
            f"成功将 {updated_count} 个工单标记为处理中。",
        )
    else:
        messages.warning(request, "没有可标记为处理中的工单。")

    return redirect("admin:admin_tickets:ticket_list")


@admin_required
@require_POST
def admin_ticket_batch_resolved(request):
    """批量标记工单为已解决"""
    selected_ids = _get_selected_ids(request)
    if not selected_ids:
        messages.warning(request, "未选择任何工单。")
        return redirect("admin:admin_tickets:ticket_list")

    qs = Ticket.objects.filter(
        pk__in=selected_ids,
        status__in=["pending", "processing", "waiting_feedback"],
    )
    site_group = getattr(request, "site_group", None)
    ticket_filter = _ticket_filter_for_user(request.user, site_group)
    if ticket_filter:
        qs = qs.filter(ticket_filter).distinct()

    updated_count = 0
    now = timezone.now()
    for ticket in qs:
        ticket.status = "resolved"
        ticket.resolved_at = now
        ticket._current_user = request.user
        ticket.save(update_fields=["status", "resolved_at", "updated_at"])
        updated_count += 1

    if updated_count > 0:
        messages.success(
            request,
            f"成功将 {updated_count} 个工单标记为已解决。",
        )
    else:
        messages.warning(request, "没有可标记为已解决的工单。")

    return redirect("admin:admin_tickets:ticket_list")


@admin_required
@require_POST
def admin_ticket_batch_closed(request):
    """批量关闭工单"""
    selected_ids = _get_selected_ids(request)
    if not selected_ids:
        messages.warning(request, "未选择任何工单。")
        return redirect("admin:admin_tickets:ticket_list")

    qs = Ticket.objects.filter(
        pk__in=selected_ids,
    ).exclude(status="closed")
    site_group = getattr(request, "site_group", None)
    ticket_filter = _ticket_filter_for_user(request.user, site_group)
    if ticket_filter:
        qs = qs.filter(ticket_filter).distinct()

    updated_count = 0
    now = timezone.now()
    for ticket in qs:
        ticket.status = "closed"
        ticket.closed_at = now
        ticket._current_user = request.user
        ticket.save(update_fields=["status", "closed_at", "updated_at"])
        updated_count += 1

    if updated_count > 0:
        messages.success(
            request,
            f"成功关闭了 {updated_count} 个工单。",
        )
    else:
        messages.warning(request, "没有可关闭的工单。")

    return redirect("admin:admin_tickets:ticket_list")


# ===========================================================================
# 工单分类管理
# ===========================================================================


@admin_required
def admin_category_list(request):
    """
    超管工单分类列表视图

    - 无数据隔离，查看所有分类
    - 支持搜索、分页
    """
    site_group = getattr(request, "site_group", None)
    category_filter = _category_filter_for_user(request.user, site_group)
    queryset = TicketCategory.objects.filter(category_filter).order_by(
        "display_order", "name"
    )

    # 搜索
    search = request.GET.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(description__icontains=search)
        )

    # 分页
    paginator = Paginator(queryset, 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "categories": page_obj,
        "search": search,
        "page_title": "工单分类",
        "active_nav": "ticket_categories",
    }

    return render(request, "admin_base/tickets/category_list.html", context)


@admin_required
def admin_category_create(request):
    """
    超管创建工单分类

    created_by 在视图中自动设置为当前用户。
    """
    if request.method == "POST":
        form = AdminTicketCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()

            messages.success(
                request,
                f"工单分类 {category.name} 创建成功",
            )
            return redirect("admin:admin_tickets:category_list")
    else:
        form = AdminTicketCategoryForm()

    context = {
        "form": form,
        "page_title": "创建工单分类",
        "active_nav": "ticket_categories",
        "is_create": True,
    }

    return render(request, "admin_base/tickets/category_form.html", context)


@admin_required
def admin_category_update(request, pk):
    """
    超管编辑工单分类

    无数据隔离，可编辑所有分类。
    """
    site_group = getattr(request, "site_group", None)
    category_filter = _category_filter_for_user(request.user, site_group)
    if category_filter:
        category = get_object_or_404(
            TicketCategory.objects.filter(category_filter),
            pk=pk,
        )
    else:
        category = get_object_or_404(TicketCategory, pk=pk)

    if request.method == "POST":
        form = AdminTicketCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(
                request,
                f"工单分类 {category.name} 更新成功",
            )
            return redirect("admin:admin_tickets:category_list")
    else:
        form = AdminTicketCategoryForm(instance=category)

    context = {
        "form": form,
        "category": category,
        "page_title": f"编辑分类 - {category.name}",
        "active_nav": "ticket_categories",
        "is_create": False,
    }

    return render(request, "admin_base/tickets/category_form.html", context)


@admin_required
def admin_category_delete(request, pk):
    """
    超管删除工单分类

    无数据隔离，可删除所有分类。
    """
    site_group = getattr(request, "site_group", None)
    category_filter = _category_filter_for_user(request.user, site_group)
    if category_filter:
        category = get_object_or_404(
            TicketCategory.objects.filter(category_filter),
            pk=pk,
        )
    else:
        category = get_object_or_404(TicketCategory, pk=pk)

    if request.method == "POST":
        category_name = category.name
        category.delete()

        messages.success(
            request,
            f"工单分类 {category_name} 已删除",
        )
        return redirect("admin:admin_tickets:category_list")

    # 获取关联工单数
    ticket_count = Ticket.objects.filter(category=category).count()

    context = {
        "category": category,
        "ticket_count": ticket_count,
        "page_title": f"删除分类 - {category.name}",
        "active_nav": "ticket_categories",
    }

    return render(request, "admin_base/tickets/category_confirm_delete.html", context)


# ===========================================================================
# 工单活动记录（只读）
# ===========================================================================


@admin_required
def admin_activity_list(request):
    """
    超管工单活动记录列表视图（只读）

    - 无数据隔离，查看所有活动记录
    - 支持按操作类型筛选、搜索
    """
    site_group = getattr(request, "site_group", None)
    ticket_filter = _ticket_filter_for_user(request.user, site_group)
    if ticket_filter:
        queryset = (
            TicketActivity.objects.filter(ticket_filter)
            .select_related(
                "ticket",
                "actor",
            )
            .order_by("-created_at")
            .distinct()
        )
    else:
        queryset = TicketActivity.objects.select_related(
            "ticket",
            "actor",
        ).order_by("-created_at")

    # 操作类型筛选
    action_filter = request.GET.get("action", "").strip()
    if action_filter:
        queryset = queryset.filter(action=action_filter)

    # 搜索
    search = request.GET.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(ticket__ticket_no__icontains=search)
            | Q(actor__username__icontains=search)
            | Q(description__icontains=search)
        )

    # 分页
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "activities": page_obj,
        "search": search,
        "action_filter": action_filter,
        "action_choices": TicketActivity.ACTION_CHOICES,
        "page_title": "活动日志",
        "active_nav": "ticket_activities",
    }

    return render(request, "admin_base/tickets/activity_list.html", context)
