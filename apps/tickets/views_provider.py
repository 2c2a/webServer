"""
工单系统 - 提供商后台视图

包含数据隔离功能：
- TicketCategory: 按 created_by 过滤（新增提供商隔离）
- Ticket: 按关联产品/主机过滤
- TicketComment: 按关联工单过滤
- TicketActivity: 按关联工单过滤（只读）
- TicketAttachment: 按关联工单过滤
"""

import os

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, TemplateView
from django.core.paginator import Paginator

from utils.provider import is_provider
from apps.provider.context_mixin import ProviderContextMixin

from .forms_provider import (
    TicketAttachmentForm,
    TicketCategoryForm,
    TicketCommentForm,
)
from .models import (
    Ticket,
    TicketActivity,
    TicketAttachment,
    TicketCategory,
    TicketComment,
)

User = get_user_model()


# ===========================================================================
# 通用 Mixin
# ===========================================================================


class ProviderTicketMixin(ProviderContextMixin):
    """
    提供商工单数据隔离 Mixin

    - dispatch: 验证提供商身份
    - get_provider_ticket_queryset: 获取当前提供商可见的工单查询集
    - get_provider_category_queryset: 获取当前提供商创建的分类查询集
    """

    provider_url_namespace = 'provider:provider_tickets'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_provider(request.user):
            return HttpResponseForbidden(
                '您没有提供商权限，无法访问此页面。'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_provider_ticket_queryset(self):
        """
        获取当前提供商可见的工单查询集

        提供商可以看到:
        - 关联云电脑所属产品由自己创建的工单
        """
        return Ticket.objects.filter(
            Q(related_cloud_computer__product__created_by=self.request.user)
        ).distinct().select_related(
            'category', 'creator', 'assignee', 'assigned_group',
            'related_cloud_computer', 'related_cloud_computer__product',
            'related_request', 'related_request__target_product',
        )

    def get_provider_category_queryset(self):
        """
        获取当前提供商创建的分类查询集

        新增提供商隔离：按 created_by 过滤
        """
        return TicketCategory.objects.filter(
            created_by=self.request.user
        ).order_by('display_order', 'name')

    def get_provider_activity_queryset(self):
        """
        获取当前提供商可见的活动记录查询集
        """
        return TicketActivity.objects.filter(
            Q(ticket__related_cloud_computer__product__created_by=self.request.user)
        ).distinct().select_related(
            'ticket', 'actor',
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'tickets'
        context['page_title'] = '工单管理'
        return context


# ===========================================================================
# 工单分类管理
# ===========================================================================


class TicketCategoryListView(ProviderTicketMixin, TemplateView):
    """
    工单分类列表视图

    - 提供商数据隔离：只看到自己创建的分类（created_by=request.user）
    - 支持搜索、分页
    """

    template_name = 'admin_base/tickets/category_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        queryset = self.get_provider_category_queryset()

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
            )

        # 分页
        paginator = Paginator(queryset, 15)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'categories': page_obj,
            'search': search,
            'page_title': '工单分类',
            'active_nav': 'ticket_categories',
        })
        return context


class TicketCategoryCreateView(ProviderTicketMixin, TemplateView):
    """
    工单分类创建视图

    自动设置 created_by 为当前用户。
    """

    template_name = 'admin_base/tickets/category_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get(
                'form',
                TicketCategoryForm(),
            ),
            'page_title': '创建工单分类',
            'active_nav': 'ticket_categories',
            'is_create': True,
        })
        return context

    def post(self, request, *args, **kwargs):
        form = TicketCategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            category.created_by = request.user
            category.save()

            messages.success(
                request,
                f'工单分类 {category.name} 创建成功',
            )
            return redirect('provider_tickets:category_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


class TicketCategoryUpdateView(ProviderTicketMixin, TemplateView):
    """
    工单分类编辑视图

    提供商数据隔离：只能编辑自己创建的分类。
    """

    template_name = 'admin_base/tickets/category_form.html'

    def get_category(self):
        """获取当前编辑的分类，确保数据隔离"""
        return get_object_or_404(
            self.get_provider_category_queryset(),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.get_category()
        form = kwargs.get(
            'form',
            TicketCategoryForm(instance=category),
        )
        context.update({
            'form': form,
            'category': category,
            'page_title': f'编辑分类 - {category.name}',
            'active_nav': 'ticket_categories',
            'is_create': False,
        })
        return context

    def post(self, request, *args, **kwargs):
        category = self.get_category()
        form = TicketCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            messages.success(
                request,
                f'工单分类 {category.name} 更新成功',
            )
            return redirect('provider_tickets:category_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


class TicketCategoryDeleteView(ProviderTicketMixin, TemplateView):
    """
    工单分类删除视图

    提供商数据隔离：只能删除自己创建的分类。
    """

    template_name = 'admin_base/tickets/category_confirm_delete.html'

    def get_category(self):
        return get_object_or_404(
            self.get_provider_category_queryset(),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.get_category()

        # 获取关联工单数
        ticket_count = Ticket.objects.filter(
            category=category
        ).count()

        context.update({
            'category': category,
            'ticket_count': ticket_count,
            'page_title': f'删除分类 - {category.name}',
            'active_nav': 'ticket_categories',
        })
        return context

    def post(self, request, *args, **kwargs):
        category = self.get_category()
        category_name = category.name
        category.delete()

        messages.success(
            request,
            f'工单分类 {category_name} 已删除',
        )
        return redirect('provider_tickets:category_list')


# ===========================================================================
# 工单管理
# ===========================================================================


class TicketListView(ProviderTicketMixin, TemplateView):
    """
    工单列表视图

    - 提供商数据隔离：只看到关联自己产品/主机的工单
    - 支持状态筛选、搜索、批量操作
    """

    template_name = 'admin_base/tickets/ticket_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        queryset = self.get_provider_ticket_queryset()

        # 状态筛选
        status_filter = self.request.GET.get('status', '').strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # 优先级筛选
        priority_filter = self.request.GET.get('priority', '').strip()
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(ticket_no__icontains=search)
                | Q(title__icontains=search)
                | Q(description__icontains=search)
            )

        # 排序
        queryset = queryset.order_by('-created_at')

        # 分页
        paginator = Paginator(queryset, 20)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # 统计各状态数量
        base_qs = self.get_provider_ticket_queryset()
        status_counts = {
            'pending': base_qs.filter(status='pending').count(),
            'processing': base_qs.filter(status='processing').count(),
            'waiting_feedback': base_qs.filter(
                status='waiting_feedback'
            ).count(),
            'resolved': base_qs.filter(status='resolved').count(),
            'closed': base_qs.filter(status='closed').count(),
        }

        context.update({
            'page_obj': page_obj,
            'tickets': page_obj,
            'search': search,
            'status_filter': status_filter,
            'priority_filter': priority_filter,
            'status_counts': status_counts,
            'status_choices': Ticket.STATUS_CHOICES,
            'priority_choices': Ticket.PRIORITY_CHOICES,
            'page_title': '工单管理',
            'active_nav': 'tickets',
        })
        return context


class TicketDetailView(ProviderTicketMixin, DetailView):
    """
    工单详情视图

    显示工单信息、评论列表、附件列表，
    支持添加评论和上传附件。
    """

    template_name = 'admin_base/tickets/ticket_detail.html'
    context_object_name = 'ticket'
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        return self.get_provider_ticket_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ticket = self.object

        # 评论列表（提供商不可见内部备注）
        comments = ticket.comments.filter(
            is_internal=False
        ).select_related('author').order_by('created_at')

        # 附件列表
        attachments = ticket.attachments.select_related(
            'uploaded_by'
        ).order_by('-created_at')

        # 活动记录
        activities = ticket.activities.select_related(
            'actor'
        ).order_by('-created_at')[:10]

        context.update({
            'comments': comments,
            'attachments': attachments,
            'activities': activities,
            'comment_form': TicketCommentForm(),
            'attachment_form': TicketAttachmentForm(),
            'page_title': f'工单 {ticket.ticket_no}',
            'active_nav': 'tickets',
        })
        return context


# ===========================================================================
# 工单批量操作
# ===========================================================================


def _get_selected_ids(request):
    """从 POST 请求中获取选中的工单 ID 列表"""
    selected = request.POST.getlist('selected_ids')
    return [int(pk) for pk in selected if pk.isdigit()]


class TicketBatchProcessingView(ProviderTicketMixin, View):
    """
    批量标记工单为处理中 (POST)
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何工单。')
            return redirect('provider_tickets:ticket_list')

        qs = self.get_provider_ticket_queryset().filter(
            pk__in=selected_ids,
            status='pending',
        )

        updated_count = 0
        for ticket in qs:
            ticket.status = 'processing'
            ticket.assignee = request.user
            ticket._current_user = request.user
            ticket.save(update_fields=['status', 'assignee', 'updated_at'])
            updated_count += 1

        if updated_count > 0:
            messages.success(
                request,
                f'成功将 {updated_count} 个工单标记为处理中。',
            )
        else:
            messages.warning(
                request,
                '没有可标记为处理中的工单。',
            )

        return redirect('provider_tickets:ticket_list')


class TicketBatchResolvedView(ProviderTicketMixin, View):
    """
    批量标记工单为已解决 (POST)
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何工单。')
            return redirect('provider_tickets:ticket_list')

        qs = self.get_provider_ticket_queryset().filter(
            pk__in=selected_ids,
            status__in=['pending', 'processing', 'waiting_feedback'],
        )

        updated_count = 0
        now = timezone.now()
        for ticket in qs:
            ticket.status = 'resolved'
            ticket.resolved_at = now
            ticket._current_user = request.user
            ticket.save(
                update_fields=['status', 'resolved_at', 'updated_at']
            )
            updated_count += 1

        if updated_count > 0:
            messages.success(
                request,
                f'成功将 {updated_count} 个工单标记为已解决。',
            )
        else:
            messages.warning(
                request,
                '没有可标记为已解决的工单。',
            )

        return redirect('provider_tickets:ticket_list')


class TicketBatchClosedView(ProviderTicketMixin, View):
    """
    批量关闭工单 (POST)
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何工单。')
            return redirect('provider_tickets:ticket_list')

        qs = self.get_provider_ticket_queryset().filter(
            pk__in=selected_ids,
        ).exclude(status='closed')

        updated_count = 0
        now = timezone.now()
        for ticket in qs:
            ticket.status = 'closed'
            ticket.closed_at = now
            ticket._current_user = request.user
            ticket.save(
                update_fields=['status', 'closed_at', 'updated_at']
            )
            updated_count += 1

        if updated_count > 0:
            messages.success(
                request,
                f'成功关闭了 {updated_count} 个工单。',
            )
        else:
            messages.warning(
                request,
                '没有可关闭的工单。',
            )

        return redirect('provider_tickets:ticket_list')


# ===========================================================================
# 工单评论
# ===========================================================================


class TicketCommentCreateView(ProviderTicketMixin, View):
    """
    添加工单评论 (POST)

    提供商添加的评论自动标记作者为当前用户。
    """

    def post(self, request, pk):
        ticket = get_object_or_404(
            self.get_provider_ticket_queryset(),
            pk=pk,
        )

        form = TicketCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.ticket = ticket
            comment.author = request.user
            comment.save()

            messages.success(request, '评论已添加。')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

        return redirect('provider_tickets:ticket_detail', pk=ticket.pk)


# ===========================================================================
# 工单活动记录（独立只读页面）
# ===========================================================================


class TicketActivityListView(ProviderTicketMixin, TemplateView):
    """
    工单活动记录列表视图（独立只读页面）

    - 提供商数据隔离：只看到关联自己工单的活动
    - 支持按操作类型筛选、搜索
    - 只读，无增删改操作
    """

    template_name = 'admin_base/tickets/activity_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        queryset = self.get_provider_activity_queryset()

        # 操作类型筛选
        action_filter = self.request.GET.get('action', '').strip()
        if action_filter:
            queryset = queryset.filter(action=action_filter)

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(ticket__ticket_no__icontains=search)
                | Q(actor__username__icontains=search)
                | Q(description__icontains=search)
            )

        # 分页
        paginator = Paginator(queryset, 20)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'activities': page_obj,
            'search': search,
            'action_filter': action_filter,
            'action_choices': TicketActivity.ACTION_CHOICES,
            'page_title': '活动日志',
            'active_nav': 'activity_log',
        })
        return context


# ===========================================================================
# 工单附件
# ===========================================================================


class TicketAttachmentUploadView(ProviderTicketMixin, View):
    """
    上传工单附件 (POST)
    """

    def post(self, request, ticket_pk):
        ticket = get_object_or_404(
            self.get_provider_ticket_queryset(),
            pk=ticket_pk,
        )

        form = TicketAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.ticket = ticket
            attachment.uploaded_by = request.user
            if not attachment.filename:
                attachment.filename = os.path.basename(
                    attachment.file.name
                )
            attachment.save()

            messages.success(request, '附件上传成功。')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)

        return redirect('provider_tickets:ticket_detail', pk=ticket.pk)


class TicketAttachmentDownloadView(ProviderTicketMixin, View):
    """
    下载工单附件
    """

    def get(self, request, pk):
        attachment = get_object_or_404(TicketAttachment, pk=pk)

        # 验证提供商是否有权访问此附件所属工单
        ticket = get_object_or_404(
            self.get_provider_ticket_queryset(),
            pk=attachment.ticket_id,
        )

        if not attachment.file:
            raise Http404('附件文件不存在')

        try:
            file_handle = attachment.file.open('rb')
        except FileNotFoundError:
            raise Http404('附件文件不存在')

        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=attachment.filename,
        )
        return response
