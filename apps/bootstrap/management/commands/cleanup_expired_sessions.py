from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.bootstrap.models import ActiveSession, InitialToken


class Command(BaseCommand):
    help = '清理过期的活动会话和初始令牌'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='仅显示将要删除的记录，不实际删除',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        now = timezone.now()

        expired_sessions = ActiveSession.objects.filter(
            expires_at__lt=now,
        )
        if expired_sessions.exists():
            count = expired_sessions.count()
            self.stdout.write(
                f'找到 {count} 个过期的会话'
            )
            if not dry_run:
                expired_sessions.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'已删除 {count} 个过期的会话'
                    )
                )

        expired_tokens = InitialToken.objects.filter(
            expires_at__lt=now,
        )
        if expired_tokens.exists():
            count = expired_tokens.count()
            self.stdout.write(
                f'找到 {count} 个过期的初始令牌'
            )
            if not dry_run:
                expired_tokens.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'已删除 {count} 个过期的初始令牌'
                    )
                )

        orphan_tokens = InitialToken.objects.filter(
            host=None,
            status='ISSUED',
            expires_at__gt=now,
        )
        if orphan_tokens.exists():
            count = orphan_tokens.count()
            self.stdout.write(
                f'找到 {count} 个未关联主机的初始令牌'
            )
            if not dry_run:
                orphan_tokens.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'已删除 {count} 个未关联主机的初始令牌'
                    )
                )

        if not any([expired_sessions.exists(), expired_tokens.exists(), orphan_tokens.exists()]):
            self.stdout.write(
                self.style.SUCCESS('没有需要清理的记录')
            )