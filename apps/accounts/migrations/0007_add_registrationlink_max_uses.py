from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def fix_existing_used_links(apps, schema_editor):
    RegistrationLink = apps.get_model('accounts', 'RegistrationLink')
    RegistrationLink.objects.filter(used=True).update(used_count=1)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_registrationlink"),
    ]

    operations = [
        migrations.AddField(
            model_name="registrationlink",
            name="max_uses",
            field=models.IntegerField(
                default=1,
                help_text="设置为0表示不限制使用次数",
                verbose_name="最大使用次数",
            ),
        ),
        migrations.AddField(
            model_name="registrationlink",
            name="used_count",
            field=models.IntegerField(default=0, verbose_name="已使用次数"),
        ),
        migrations.AlterField(
            model_name="registrationlink",
            name="used_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="最后使用时间"
            ),
        ),
        migrations.AlterField(
            model_name="registrationlink",
            name="used_by",
            field=models.ForeignKey(
                blank=True,
                help_text="最后使用此链接注册的用户",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="used_registration_link",
                to=settings.AUTH_USER_MODEL,
                verbose_name="最后使用者",
            ),
        ),
        migrations.RunPython(fix_existing_used_links, migrations.RunPython.noop),
    ]
