from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('operations', '0015_alter_rdpdomainroute_domain_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='limit_one_per_user',
            field=models.BooleanField(default=False, help_text='是否限制每个用户只能拥有一个此产品', verbose_name='每人限购一个'),
        ),
    ]
