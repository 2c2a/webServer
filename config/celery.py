import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('2c2a')
app.config_from_object('django.conf:settings', namespace='CELERY')

from django.conf import settings  # noqa: E402

_redis_url = getattr(settings, 'REDIS_URL', '')
_base_dir = str(settings.BASE_DIR)

if not app.conf.broker_url:
    _broker = getattr(settings, 'CELERY_BROKER_URL', None)
    if _broker:
        app.conf.broker_url = _broker
    elif _redis_url:
        app.conf.broker_url = _redis_url.replace('/0', '/1')
    else:
        app.conf.broker_url = (
            f'sqla+sqlite:///{_base_dir}/celery_broker.sqlite3'
        )

if not app.conf.result_backend:
    _result = getattr(settings, 'CELERY_RESULT_BACKEND', None)
    if _result:
        app.conf.result_backend = _result
    elif _redis_url:
        app.conf.result_backend = _redis_url.replace('/0', '/2')
    else:
        app.conf.result_backend = (
            f'db+sqlite:///{_base_dir}/celery_results.sqlite3'
        )

app.autodiscover_tasks()

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

app.conf.task_routes = {
    'certificates.tasks.*': {'queue': 'certificates'},
    'hosts.tasks.*': {'queue': 'hosts'},
    'operations.tasks.*': {'queue': 'operations'},
    'bootstrap.tasks.*': {'queue': 'bootstrap'},
    'plugins.beta_push.tasks.*': {'queue': 'beta_push'},
    'accounts.tasks.*': {'queue': 'accounts'},
}

app.conf.task_default_retry_delay = 30
app.conf.task_max_retries = 3

app.conf.CELERY_BEAT_SCHEDULE = {
    'cleanup-expired-provision-tokens': {
        'task': 'apps.bootstrap.tasks.cleanup_expired_provision_tokens',
        'schedule': crontab(hour='0', minute='0'),
    },
    'cleanup-unactivated-certificates': {
        'task': 'apps.bootstrap.tasks.cleanup_unactivated_certificates',
        'schedule': crontab(hour='0', minute='0'),
    },
    'cleanup-orphan-cert-dirs': {
        'task': 'apps.bootstrap.tasks.cleanup_orphan_cert_dirs',
        'schedule': crontab(hour='0', minute='0'),
    },
}
