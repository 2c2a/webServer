from django.core.management.base import BaseCommand
from django.core.cache import cache
from apps.dashboard.models import SystemConfig, SiteGroup, SiteGroupHostname


class Command(BaseCommand):
    help = '将 SystemConfig.hostname_branding 数据迁移到 SiteGroup 模型'

    def handle(self, *args, **options):
        try:
            config = SystemConfig.get_config()
        except SystemConfig.DoesNotExist:
            self.stdout.write(self.style.ERROR('SystemConfig 不存在'))
            return

        if not config.hostname_branding:
            self.stdout.write(self.style.WARNING('hostname_branding 为空，无需迁移'))
            return

        created_count = 0
        hostname_count = 0

        for hostname, branding in config.hostname_branding.items():
            site_name = branding.get('site_name', '')
            site_icon = branding.get('site_icon', '')

            if not site_name and not site_icon:
                continue

            slug = hostname.replace('.', '-').replace(':', '-')
            site_group, created = SiteGroup.objects.get_or_create(
                slug=slug,
                defaults={
                    'name': site_name or hostname,
                    'site_name': site_name,
                    'site_icon': site_icon,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'创建站点组: {site_group.name} (slug={slug})'))
            else:
                updated = False
                if site_name and not site_group.site_name:
                    site_group.site_name = site_name
                    updated = True
                if site_icon and not site_group.site_icon:
                    site_group.site_icon = site_icon
                    updated = True
                if updated:
                    site_group.save()
                    self.stdout.write(f'更新站点组: {site_group.name}')

            _, hn_created = SiteGroupHostname.objects.get_or_create(
                hostname=hostname,
                defaults={'site_group': site_group}
            )
            if hn_created:
                hostname_count += 1
                self.stdout.write(f'绑定主机名: {hostname} -> {site_group.name}')

        cache.delete_pattern('site_group:hostname:*') if hasattr(cache, 'delete_pattern') else None

        self.stdout.write(self.style.SUCCESS(
            f'\n迁移完成: 创建 {created_count} 个站点组, 绑定 {hostname_count} 个主机名'
        ))
