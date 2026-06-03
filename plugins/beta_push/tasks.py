import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=10)
def push_to_beta(self, user_id, sync_log_id, site_group_id=None):
    from .models import SyncLog
    from .services import BetaPushService

    try:
        sync_log = SyncLog.objects.get(pk=sync_log_id)
    except SyncLog.DoesNotExist:
        logger.error(f'SyncLog {sync_log_id} 不存在')
        return

    sync_log.status = 'running'
    sync_log.started_at = timezone.now()
    sync_log.task_id = self.request.id
    sync_log.save(update_fields=['status', 'started_at', 'task_id'])

    try:
        service = BetaPushService(
            user_id=user_id,
            task_id=self.request.id,
            site_group_id=site_group_id,
        )
        stats = service.push_all()

        sync_log.status = 'success'
        sync_log.records_pushed = stats['pushed']
        sync_log.records_skipped = stats['skipped']
        sync_log.records_failed = stats['failed']
        if stats['errors']:
            sync_log.error_message = '\n'.join(stats['errors'][:20])
        sync_log.completed_at = timezone.now()
        sync_log.save()

        logger.info(
            f'Beta推送完成: user={user_id}, '
            f'pushed={stats["pushed"]}, '
            f'skipped={stats["skipped"]}, '
            f'failed={stats["failed"]}'
        )

    except Exception as e:
        logger.error(f'Beta推送失败: user={user_id}, error={e}', exc_info=True)
        sync_log.status = 'failed'
        sync_log.error_message = str(e)[:2000]
        sync_log.completed_at = timezone.now()
        sync_log.save()
        raise self.retry(exc=e)
