import logging

from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone

from apps.accounts.provider_decorators import is_provider, is_site_group_admin

from .models import SyncLog
from .services import get_progress

User = get_user_model()
logger = logging.getLogger(__name__)


def _check_permission(user, site_group=None):
    if user.is_superuser:
        return True
    if is_site_group_admin(user, site_group):
        return True
    return is_provider(user)


def dashboard(request):
    site_group = getattr(request, "site_group", None)
    if not _check_permission(request.user, site_group):
        from django.http import HttpResponseForbidden

        return HttpResponseForbidden("仅主机提供商及以上权限用户可使用此功能")

    from . import is_beta_db_configured
    from django.conf import settings

    beta_configured = is_beta_db_configured() and "beta" in settings.DATABASES

    sync_logs = SyncLog.objects.filter(user=request.user).order_by("-created_at")[:10]

    is_running = sync_logs.filter(status="running").exists() if sync_logs else False

    last_success = None
    for log in sync_logs:
        if log.status == "success":
            last_success = log
            break

    running_task_id = ""
    if is_running:
        running_log = sync_logs.filter(status="running").first()
        running_task_id = running_log.task_id if running_log else ""

    context = {
        "page_title": "Beta数据推送",
        "active_nav": "beta_push",
        "beta_configured": beta_configured,
        "sync_logs": sync_logs,
        "is_running": is_running,
        "last_success": last_success,
        "running_task_id": running_task_id,
    }

    return render(request, "beta_push/dashboard.html", context)


@require_POST
def start_push(request):
    site_group = getattr(request, "site_group", None)
    if not _check_permission(request.user, site_group):
        return JsonResponse({"success": False, "error": "权限不足"}, status=403)

    from . import is_beta_db_configured
    from django.conf import settings

    if not is_beta_db_configured() or "beta" not in settings.DATABASES:
        return JsonResponse({"success": False, "error": "Beta数据库未配置"}, status=400)

    if SyncLog.objects.filter(user=request.user, status="running").exists():
        return JsonResponse(
            {"success": False, "error": "已有推送任务正在执行"}, status=409
        )

    sync_log = SyncLog.objects.create(
        user=request.user,
        status="pending",
    )

    try:
        from .tasks import push_to_beta

        result = push_to_beta.delay(
            request.user.pk,
            sync_log.pk,
            site_group_id=site_group.pk if site_group else None,
        )
        sync_log.task_id = result.id
        sync_log.save(update_fields=["task_id"])

        return JsonResponse(
            {
                "success": True,
                "task_id": result.id,
                "sync_log_id": sync_log.pk,
            }
        )
    except Exception as e:
        logger.error(f"启动Beta推送任务失败: {e}", exc_info=True)
        sync_log.status = "failed"
        sync_log.error_message = str(e)
        sync_log.save()
        return JsonResponse({"success": False, "error": "任务启动失败"}, status=500)


def push_status(request):
    site_group = getattr(request, "site_group", None)
    if not _check_permission(request.user, site_group):
        return JsonResponse({"success": False, "error": "权限不足"}, status=403)

    task_id = request.GET.get("task_id", "")
    if not task_id:
        latest_log = (
            SyncLog.objects.filter(user=request.user).order_by("-created_at").first()
        )
        if not latest_log:
            return JsonResponse({"success": True, "status": "none"})
        return JsonResponse(
            {
                "success": True,
                "status": latest_log.status,
                "records_pushed": latest_log.records_pushed,
                "records_skipped": latest_log.records_skipped,
                "records_failed": latest_log.records_failed,
                "error_message": latest_log.error_message,
                "completed_at": (
                    latest_log.completed_at.isoformat()
                    if latest_log.completed_at
                    else None
                ),
            }
        )

    progress = get_progress(task_id)

    sync_log = (
        SyncLog.objects.filter(
            user=request.user,
            task_id=task_id,
        )
        .order_by("-created_at")
        .first()
    )

    response_data = {
        "success": True,
        "progress": progress,
    }

    if sync_log:
        response_data.update(
            {
                "status": sync_log.status,
                "records_pushed": sync_log.records_pushed,
                "records_skipped": sync_log.records_skipped,
                "records_failed": sync_log.records_failed,
                "error_message": sync_log.error_message,
                "completed_at": (
                    sync_log.completed_at.isoformat() if sync_log.completed_at else None
                ),
            }
        )

    return JsonResponse(response_data)
