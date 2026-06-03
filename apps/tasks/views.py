import logging

from django.http import JsonResponse
from django.contrib.auth.decorators import login_required

from apps.tasks.models import AsyncTask

logger = logging.getLogger(__name__)


@login_required
def async_task_status(request, task_id):
    try:
        task = AsyncTask.objects.get(task_id=task_id)
    except AsyncTask.DoesNotExist:
        return JsonResponse(
            {'success': False, 'error': '任务不存在'},
            status=404,
        )

    data = {
        'success': True,
        'task_id': task.task_id,
        'name': task.name,
        'status': task.status,
        'progress': task.progress,
        'created_at': task.created_at.isoformat() if task.created_at else None,
        'started_at': task.started_at.isoformat() if task.started_at else None,
        'completed_at': task.completed_at.isoformat() if task.completed_at else None,
        'error_message': task.error_message,
    }

    if task.status in ('success', 'failed') and task.result:
        if isinstance(task.result, dict):
            data.update(task.result)

    return JsonResponse(data)
