"""
工单系统视图
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView, UpdateView
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseRedirect
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta

from .models import Ticket, TicketComment, TicketActivity, TicketCategory
from .forms import (
    TicketForm, TicketCommentForm, TicketAssignForm,
    TicketStatusForm, TicketCloseForm, TicketFilterForm
)


class TicketListView(LoginRequiredMixin, ListView):
    """
    工单列表视图
    """
    model = Ticket
    template_name = 'tickets/ticket_list.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        """获取查询集"""
        queryset = Ticket.objects.all()
        user = self.request.user

        # 权限过滤
        if not (user.is_staff or user.is_superuser):
            # 普通用户只能看到自己创建的工单
            queryset = queryset.filter(creator=user)

        # 应用过滤条件
        form = TicketFilterForm(self.request.GET)
        if form.is_valid():
            status = form.cleaned_data.get('status')
            priority = form.cleaned_data.get('priority')
            category = form.cleaned_data.get('category')
            search = form.cleaned_data.get('search')
            start_date = form.cleaned_data.get('start_date')
            end_date = form.cleaned_data.get('end_date')

            if status:
                queryset = queryset.filter(status=status)
            if priority:
                queryset = queryset.filter(priority=priority)
            if category:
                queryset = queryset.filter(category=category)
            if search:
                queryset = queryset.filter(
                    Q(ticket_no__icontains=search[:50]) |
                    Q(title__icontains=search[:50]) |
                    Q(description__icontains=search[:50])
                )
            if start_date:
                queryset = queryset.filter(created_at__gte=start_date)
            if end_date:
                end_date = end_date + timedelta(days=1)
                queryset = queryset.filter(created_at__lt=end_date)

        return queryset.select_related('creator', 'assignee', 'category').order_by('-created_at')

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['statuses'] = Ticket.STATUS_CHOICES
        context['priorities'] = Ticket.PRIORITY_CHOICES
        context['categories'] = TicketCategory.objects.filter(is_active=True)
        return context


class MyTicketsView(LoginRequiredMixin, ListView):
    """
    我的工单视图
    """
    model = Ticket
    template_name = 'tickets/my_tickets.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        """获取当前用户的工单"""
        queryset = Ticket.objects.filter(creator=self.request.user)

        # 应用过滤条件
        form = TicketFilterForm(self.request.GET)
        if form.is_valid():
            status = form.cleaned_data.get('status')
            if status:
                queryset = queryset.filter(status=status)

        return queryset.select_related('assignee', 'category').order_by('-created_at')

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context['filter_form'] = TicketFilterForm(self.request.GET)
        context['statuses'] = Ticket.STATUS_CHOICES
        return context


class PendingTicketsView(LoginRequiredMixin, ListView):
    """
    待处理工单视图（管理员/处理人）
    """
    model = Ticket
    template_name = 'tickets/pending_list.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        """获取待处理工单"""
        user = self.request.user
        queryset = Ticket.objects.filter(status__in=['pending', 'processing', 'waiting_feedback'])

        if not (user.is_staff or user.is_superuser):
            # 非管理员只能看到分配给自己或自己所在用户组的
            user_groups = user.groups.all()
            queryset = queryset.filter(
                Q(assignee=user) | Q(assigned_group__in=user_groups)
            )

        return queryset.select_related(
            'creator', 'assignee', 'assigned_group', 'category'
        ).order_by('due_at', '-priority', '-created_at')

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context['statuses'] = Ticket.STATUS_CHOICES
        return context


class TicketCreateView(LoginRequiredMixin, CreateView):
    """
    创建工单视图
    """
    model = Ticket
    form_class = TicketForm
    template_name = 'tickets/ticket_form.html'
    success_url = reverse_lazy('tickets:my_tickets')

    def get_form_kwargs(self):
        """获取表单初始化参数"""
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        """表单验证成功后的处理"""
        # 封禁用户只能提交允许的分类
        from apps.accounts.models import UserBan
        if UserBan.objects.filter(user=self.request.user).exists():
            category = form.instance.category
            if not category or not category.allow_banned_users:
                messages.error(self.request, '您只能在被允许的分类下提交工单')
                return self.form_invalid(form)

        form.instance.creator = self.request.user
        form.instance.status = 'pending'
        form.instance.source = 'web'

        # 如果有分类，自动分配
        if form.instance.category:
            if form.instance.category.auto_assign_to:
                form.instance.assignee = form.instance.category.auto_assign_to
            if form.instance.category.auto_assign_to_group:
                form.instance.assigned_group = form.instance.category.auto_assign_to_group

        response = super().form_valid(form)

        # 记录创建活动
        TicketActivity.objects.create(
            ticket=self.object,
            actor=self.request.user,
            action='create',
            description='创建工单'
        )

        messages.success(self.request, f'工单 {self.object.ticket_no} 已成功创建！')
        return response

    def form_invalid(self, form):
        """表单验证失败后的处理"""
        messages.error(self.request, '工单信息填写有误，请检查输入信息。')
        return super().form_invalid(form)


class TicketDetailView(LoginRequiredMixin, DetailView):
    """
    工单详情视图
    """
    model = Ticket
    template_name = 'tickets/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        """获取查询集"""
        return Ticket.objects.select_related(
            'creator', 'assignee', 'assigned_group', 'category',
            'related_product', 'related_host'
        ).prefetch_related('comments', 'activities')

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        ticket = self.object
        user = self.request.user

        # 权限检查
        can_view = (
            ticket.creator == user or
            ticket.assignee == user or
            user.is_staff or
            user.is_superuser or
            (ticket.assigned_group and user.groups.filter(pk=ticket.assigned_group.pk).exists())
        )

        if not can_view:
            context['forbidden'] = True
            return context

        # 评论表单
        context['comment_form'] = TicketCommentForm()

        # 分配表单（仅管理员/工作人员）
        if user.is_staff or user.is_superuser:
            context['assign_form'] = TicketAssignForm()
            context['status_form'] = TicketStatusForm()

        # 关闭表单（创建者或管理员）
        if ticket.creator == user or user.is_staff or user.is_superuser:
            context['close_form'] = TicketCloseForm()

        # 评论列表（过滤内部备注）
        comments = ticket.comments.all()
        if not (user.is_staff or user.is_superuser):
            comments = comments.filter(is_internal=False)
        context['comments'] = comments

        # 活动记录
        context['activities'] = ticket.activities.all()[:20]

        # 状态流转选项
        context['status_choices'] = Ticket.STATUS_CHOICES

        return context


@login_required
def ticket_assign(request, pk):
    """
    分配工单
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    # 权限检查
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('无权操作')

    if request.method == 'POST':
        form = TicketAssignForm(request.POST)
        if form.is_valid():
            assignee = form.cleaned_data.get('assignee')
            assigned_group = form.cleaned_data.get('assigned_group')
            notes = form.cleaned_data['notes']

            old_assignee = ticket.assignee
            old_assigned_group = ticket.assigned_group
            ticket.assign_to(
                user=assignee,
                group=assigned_group,
                actor=request.user,
            )

            # 构建分配描述
            assign_desc_parts = []
            if assignee:
                assign_desc_parts.append(f'{assignee.username}')
            if assigned_group:
                assign_desc_parts.append(f'{assigned_group.name}(组)')

            # 记录活动
            TicketActivity.objects.create(
                ticket=ticket,
                actor=request.user,
                action='assign',
                old_value=str(old_assignee) if old_assignee else '',
                new_value=' / '.join(assign_desc_parts),
                description=f'工单分配给 {" / ".join(assign_desc_parts)}' + (f'，备注: {notes}' if notes else '')
            )

            messages.success(request, f'工单已分配给 {" / ".join(assign_desc_parts)}')
            return redirect('tickets:ticket_detail', pk=ticket.pk)

    return redirect('tickets:ticket_detail', pk=ticket.pk)


@login_required
def ticket_status_update(request, pk):
    """
    更新工单状态
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    # 权限检查
    if not (request.user.is_staff or request.user.is_superuser or request.user == ticket.assignee or
            (ticket.assigned_group and request.user.groups.filter(pk=ticket.assigned_group.pk).exists())):
        return HttpResponseForbidden('无权操作')

    if request.method == 'POST':
        form = TicketStatusForm(request.POST)
        if form.is_valid():
            new_status = form.cleaned_data['status']
            notes = form.cleaned_data['notes']

            old_status = ticket.status
            ticket.update_status(new_status, actor=request.user)

            # 记录活动
            TicketActivity.objects.create(
                ticket=ticket,
                actor=request.user,
                action='status_change',
                old_value=old_status,
                new_value=new_status,
                description=f'状态变更为 {ticket.get_status_display()}' + (f'，备注: {notes}' if notes else '')
            )

            messages.success(request, f'工单状态已更新为 {ticket.get_status_display()}')
            return redirect('tickets:ticket_detail', pk=ticket.pk)

    return redirect('tickets:ticket_detail', pk=ticket.pk)


@login_required
def ticket_close(request, pk):
    """
    关闭工单
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    # 权限检查
    if not (request.user == ticket.creator or request.user.is_staff or request.user.is_superuser):
        return HttpResponseForbidden('无权操作')

    if request.method == 'POST':
        form = TicketCloseForm(request.POST)
        if form.is_valid():
            satisfaction = form.cleaned_data['satisfaction']
            comment = form.cleaned_data['satisfaction_comment']

            satisfaction_int = int(satisfaction) if satisfaction else None

            ticket.close(
                actor=request.user,
                satisfaction=satisfaction_int,
                comment=comment
            )

            # 记录活动
            TicketActivity.objects.create(
                ticket=ticket,
                actor=request.user,
                action='close',
                description='关闭工单' + (f'，满意度: {satisfaction}' if satisfaction else '')
            )

            messages.success(request, '工单已关闭')
            return redirect('tickets:ticket_detail', pk=ticket.pk)

    return redirect('tickets:ticket_detail', pk=ticket.pk)


@login_required
@require_POST
def ticket_comment(request, pk):
    """
    添加工单评论
    """
    ticket = get_object_or_404(Ticket, pk=pk)

    # 权限检查
    can_comment = (
        ticket.creator == request.user or
        ticket.assignee == request.user or
        request.user.is_staff or
        request.user.is_superuser or
        (ticket.assigned_group and request.user.groups.filter(pk=ticket.assigned_group.pk).exists())
    )

    if not can_comment:
        return HttpResponseForbidden('无权评论')

    form = TicketCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.ticket = ticket
        comment.author = request.user

        # 非工作人员不能添加内部备注
        if comment.is_internal and not (request.user.is_staff or request.user.is_superuser):
            comment.is_internal = False

        comment.save()

        messages.success(request, '评论已添加')
    else:
        messages.error(request, '评论内容无效')

    return redirect('tickets:ticket_detail', pk=ticket.pk)


class TicketDashboardView(LoginRequiredMixin, ListView):
    """
    工单仪表盘视图
    """
    model = Ticket
    template_name = 'tickets/dashboard.html'
    context_object_name = 'tickets'
    paginate_by = 10

    def get_queryset(self):
        """获取最近工单"""
        user = self.request.user
        queryset = Ticket.objects.all()

        if not (user.is_staff or user.is_superuser):
            queryset = queryset.filter(creator=user)

        return queryset.select_related('creator', 'assignee', 'category').order_by('-created_at')[:10]

    def get_context_data(self, **kwargs):
        """获取统计信息"""
        context = super().get_context_data(**kwargs)
        user = self.request.user

        if user.is_staff or user.is_superuser:
            # 管理员统计
            context['total_tickets'] = Ticket.objects.count()
            context['pending_count'] = Ticket.objects.filter(status='pending').count()
            context['processing_count'] = Ticket.objects.filter(status='processing').count()
            context['resolved_count'] = Ticket.objects.filter(status='resolved').count()
            context['closed_count'] = Ticket.objects.filter(status='closed').count()
            context['overdue_count'] = Ticket.objects.filter(
                due_at__lt=timezone.now()
            ).exclude(status__in=['resolved', 'closed', 'rejected']).count()
        else:
            # 用户统计
            context['total_tickets'] = Ticket.objects.filter(creator=user).count()
            context['pending_count'] = Ticket.objects.filter(creator=user, status='pending').count()
            context['processing_count'] = Ticket.objects.filter(creator=user, status='processing').count()
            context['resolved_count'] = Ticket.objects.filter(creator=user, status='resolved').count()
            context['closed_count'] = Ticket.objects.filter(creator=user, status='closed').count()

        # 优先级分布
        context['priority_distribution'] = {
            'urgent': Ticket.objects.filter(priority='urgent').count() if (user.is_staff or user.is_superuser) else Ticket.objects.filter(creator=user, priority='urgent').count(),
            'high': Ticket.objects.filter(priority='high').count() if (user.is_staff or user.is_superuser) else Ticket.objects.filter(creator=user, priority='high').count(),
            'medium': Ticket.objects.filter(priority='medium').count() if (user.is_staff or user.is_superuser) else Ticket.objects.filter(creator=user, priority='medium').count(),
            'low': Ticket.objects.filter(priority='low').count() if (user.is_staff or user.is_superuser) else Ticket.objects.filter(creator=user, priority='low').count(),
        }

        return context
