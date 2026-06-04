import logging

from django.db import migrations, models

logger = logging.getLogger(__name__)


def migrate_ca_to_files(apps, schema_editor):
    CertificateAuthority = apps.get_model('certificates', 'CertificateAuthority')
    import secrets
    import os
    from django.conf import settings
    from pathlib import Path

    ca_base_dir = Path(settings.MEDIA_ROOT) / 'certificates' / 'ca'

    for ca in CertificateAuthority.objects.all():
        raw_key = ca.__dict__.get('_private_key') or ca.__dict__.get('private_key')
        raw_cert = ca.__dict__.get('certificate')

        if not raw_key or not raw_cert:
            ca.is_active = False
            ca.cert_dir = ''
            ca.save()
            logger.warning(
                f"CA {ca.name} has no key/cert data, marked inactive"
            )
            continue

        try:
            import base64
            import hashlib
            from cryptography.fernet import Fernet, InvalidToken

            key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
            fernet = Fernet(base64.urlsafe_b64encode(key))
            decrypted_key = fernet.decrypt(raw_key.encode()).decode()

            cert_dir_name = secrets.token_hex(8)
            ca_dir = ca_base_dir / cert_dir_name
            ca_dir.mkdir(parents=True, exist_ok=True)

            key_path = ca_dir / 'ca.key'
            key_path.write_text(decrypted_key, encoding='utf-8')
            os.chmod(key_path, 0o600)

            cert_path = ca_dir / 'ca.crt'
            cert_path.write_text(raw_cert, encoding='utf-8')
            os.chmod(cert_path, 0o600)

            ca.cert_dir = cert_dir_name
            ca.save()
            logger.info(f"CA {ca.name} migrated to files at {cert_dir_name}")
        except (InvalidToken, Exception) as e:
            ca.is_active = False
            ca.cert_dir = ''
            ca.save()
            logger.warning(
                f"CA {ca.name} key decryption failed ({e}), "
                f"marked inactive for re-creation"
            )


def reverse_migrate(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("certificates", "0005_remove_cert_content_from_db"),
    ]

    operations = [
        migrations.AddField(
            model_name="certificateauthority",
            name="cert_dir",
            field=models.CharField(
                blank=True, default="", max_length=64, verbose_name="证书目录"
            ),
        ),
        migrations.RunPython(migrate_ca_to_files, reverse_migrate),
        migrations.RemoveField(
            model_name="certificateauthority",
            name="_private_key",
        ),
        migrations.RemoveField(
            model_name="certificateauthority",
            name="certificate",
        ),
    ]
