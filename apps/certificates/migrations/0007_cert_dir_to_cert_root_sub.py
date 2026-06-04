import logging
import os
import shutil
import secrets

from django.db import migrations, models
from pathlib import Path
from django.conf import settings

logger = logging.getLogger(__name__)


def migrate_cert_dir_to_root_sub(apps, schema_editor):
    CertificateAuthority = apps.get_model(
        'certificates', 'CertificateAuthority'
    )
    ca_base_dir = Path(settings.MEDIA_ROOT) / 'certificates' / 'ca'

    for ca in CertificateAuthority.objects.all():
        old_dir_name = ca.cert_dir
        if not old_dir_name:
            ca.cert_root = ''
            ca.cert_sub = ''
            ca.save()
            continue

        old_dir = ca_base_dir / old_dir_name
        if not old_dir.exists():
            logger.warning(
                f"CA {ca.name}: old dir {old_dir} not found, "
                f"generating new paths"
            )
            ca.cert_root = ''
            ca.cert_sub = ''
            ca.save()
            continue

        cert_root = secrets.token_hex(1)
        cert_sub = secrets.token_hex(1)
        new_dir = ca_base_dir / cert_root / cert_sub
        new_dir.mkdir(parents=True, exist_ok=True)

        for fname in os.listdir(old_dir):
            src = old_dir / fname
            dst = new_dir / fname
            shutil.move(str(src), str(dst))

        shutil.rmtree(old_dir)
        try:
            old_dir.parent.rmdir()
        except OSError as exc:
            logger.debug(
                f"CA {ca.name}: could not remove parent dir {old_dir.parent}: {exc}"
            )

        ca.cert_root = cert_root
        ca.cert_sub = cert_sub
        ca.save()
        logger.info(
            f"CA {ca.name}: moved from {old_dir_name} "
            f"to {cert_root}/{cert_sub}"
        )


def reverse_migrate(apps, schema_editor):
    CertificateAuthority = apps.get_model(
        'certificates', 'CertificateAuthority'
    )
    ca_base_dir = Path(settings.MEDIA_ROOT) / 'certificates' / 'ca'

    for ca in CertificateAuthority.objects.all():
        if not ca.cert_root or not ca.cert_sub:
            ca.cert_dir = ''
            ca.save()
            continue

        new_dir_name = secrets.token_hex(8)
        new_dir = ca_base_dir / new_dir_name
        old_dir = ca_base_dir / ca.cert_root / ca.cert_sub

        if old_dir.exists():
            new_dir.mkdir(parents=True, exist_ok=True)
            for fname in os.listdir(old_dir):
                src = old_dir / fname
                dst = new_dir / fname
                shutil.move(str(src), str(dst))
            shutil.rmtree(old_dir)
            try:
                old_dir.parent.rmdir()
            except OSError as exc:
                logger.debug(
                    f"CA {ca.name}: could not remove parent dir {old_dir.parent}: {exc}"
                )

        ca.cert_dir = new_dir_name
        ca.save()


class Migration(migrations.Migration):

    dependencies = [
        (
            "certificates",
            "0006_remove_certificateauthority__private_key_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="certificateauthority",
            name="cert_root",
            field=models.CharField(
                blank=True,
                default="",
                max_length=2,
                verbose_name="证书存储根路径",
            ),
        ),
        migrations.AddField(
            model_name="certificateauthority",
            name="cert_sub",
            field=models.CharField(
                blank=True,
                default="",
                max_length=2,
                verbose_name="证书存储子路径",
            ),
        ),
        migrations.RunPython(
            migrate_cert_dir_to_root_sub, reverse_migrate
        ),
        migrations.RemoveField(
            model_name="certificateauthority",
            name="cert_dir",
        ),
    ]
