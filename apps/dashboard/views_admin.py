"""
仪表盘超级管理员视图

包含：
- DashboardWidget CRUD
- SystemConfig 单例编辑 + 发送测试邮件
"""

import json
import logging

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.provider_decorators import superadmin_required
from .models import DashboardWidget, SystemConfig
from .forms_admin import DashboardWidgetForm, SystemConfigForm

logger = logging.getLogger('2c2a')


# ============================================================
# DashboardWidget CRUD
# ============================================================

@superadmin_required
def widget_list(request):
    """仪表盘组件列表"""
    queryset = DashboardWidget.objects.order_by('display_order')

    search = request.GET.get('search', '').strip()
    if search:
        queryset = queryset.filter(
            title__icontains=search
        ) | queryset.filter(
            widget_type__icontains=search
        )

    paginator = Paginator(queryset, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'active_nav': 'dashboard_widgets',
    }
    return render(request, 'admin_base/dashboard/widget_list.html', context)


@superadmin_required
def widget_create(request):
    """创建仪表盘组件"""
    if request.method == 'POST':
        form = DashboardWidgetForm(request.POST)
        if form.is_valid():
            widget = form.save()
            messages.success(
                request, f'仪表盘组件「{widget.title}」创建成功。'
            )
            return redirect('admin:admin_dashboard_config:widget_list')
    else:
        form = DashboardWidgetForm()

    context = {
        'form': form,
        'active_nav': 'dashboard_widgets',
        'is_create': True,
    }
    return render(request, 'admin_base/dashboard/widget_form.html', context)


@superadmin_required
def widget_edit(request, pk):
    """编辑仪表盘组件"""
    widget = get_object_or_404(DashboardWidget, pk=pk)

    if request.method == 'POST':
        form = DashboardWidgetForm(request.POST, instance=widget)
        if form.is_valid():
            widget = form.save()
            messages.success(
                request, f'仪表盘组件「{widget.title}」更新成功。'
            )
            return redirect('admin:admin_dashboard_config:widget_list')
    else:
        form = DashboardWidgetForm(instance=widget)

    context = {
        'form': form,
        'widget': widget,
        'active_nav': 'dashboard_widgets',
        'is_create': False,
    }
    return render(request, 'admin_base/dashboard/widget_form.html', context)


@superadmin_required
def widget_delete(request, pk):
    """删除仪表盘组件"""
    widget = get_object_or_404(DashboardWidget, pk=pk)

    if request.method == 'POST':
        title = widget.title
        widget.delete()
        messages.success(
            request, f'仪表盘组件「{title}」已删除。'
        )
        return redirect('admin:admin_dashboard_config:widget_list')

    context = {
        'widget': widget,
        'active_nav': 'dashboard_widgets',
    }
    return render(
        request, 'admin_base/dashboard/widget_confirm_delete.html', context
    )


# ============================================================
# SystemConfig 单例编辑 + 发送测试邮件
# ============================================================

@superadmin_required
def systemconfig_edit(request):
    """系统配置编辑（单例，自动 get_or_create）"""
    config, _ = SystemConfig.objects.get_or_create(pk=1)

    if request.method == 'POST':
        form = SystemConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            from .signals import system_config_saved
            system_config_saved.send(
                sender=SystemConfig,
                request=request,
            )
            messages.success(request, '系统配置已更新。')
            return redirect('admin:admin_dashboard_config:systemconfig_edit')
    else:
        form = SystemConfigForm(instance=config)

    context = {
        'form': form,
        'config': config,
        'active_nav': 'dashboard_config',
    }
    return render(
        request, 'admin_base/dashboard/systemconfig_edit.html', context
    )


@superadmin_required
@require_POST
def systemconfig_send_test_email(request):
    """发送测试邮件（异步，跳转中间页通过 SSE 追踪状态）"""
    config = get_object_or_404(SystemConfig, pk=1)

    test_email = (
        request.POST.get('test_email')
        or request.user.email
        or config.smtp_from_email
    )

    if not test_email:
        messages.error(request, '未提供测试邮箱地址。')
        return redirect('admin:admin_dashboard_config:systemconfig_edit')

    # 创建 AsyncTask 追踪记录
    from apps.tasks.models import AsyncTask
    task_record = AsyncTask.objects.create(
        name='测试邮件发送',
        created_by=request.user,
        status='pending',
        result={'test_email': test_email},
    )

    # 派发 Celery 任务
    from apps.accounts.tasks import send_test_email_task
    send_test_email_task.delay(task_record.pk)

    # 跳转到中间页
    return redirect(
        'admin:admin_dashboard_config:test_email_progress',
        task_pk=task_record.pk
    )


@superadmin_required
def test_email_progress(request, task_pk):
    """测试邮件发送进度中间页"""
    from apps.tasks.models import AsyncTask
    task_record = get_object_or_404(AsyncTask, pk=task_pk)

    # 安全检查：只允许创建者或超管查看
    if (
        task_record.created_by != request.user
        and not request.user.is_superuser
    ):
        messages.error(request, '无权查看此任务。')
        return redirect('admin:admin_dashboard_config:systemconfig_edit')

    context = {
        'task_record': task_record,
        'test_email': (
            task_record.result.get('test_email', '')
            if task_record.result else ''
        ),
        'active_nav': 'dashboard_config',
    }
    return render(
        request,
        'admin_base/dashboard/test_email_progress.html',
        context,
    )


@superadmin_required
def test_email_sse(request, task_pk):
    """测试邮件发送状态 SSE 端点"""
    from apps.tasks.models import AsyncTask
    import time

    def event_stream():
        for _ in range(120):  # 最多等待 60 秒
            try:
                task_record = AsyncTask.objects.get(pk=task_pk)
            except AsyncTask.DoesNotExist:
                yield f"data: {json.dumps({'status': 'failed', 'error': '任务不存在'})}\n\n"
                return

            data = {
                'status': task_record.status,
                'progress': task_record.progress,
                'error': task_record.error_message,
            }
            yield f"data: {json.dumps(data)}\n\n"

            if task_record.status in ('success', 'failed', 'cancelled'):
                return

            time.sleep(0.5)

        # 超时
        yield f"data: {json.dumps({'status': 'timeout'})}\n\n"

    response = StreamingHttpResponse(
        event_stream(), content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
