from django.apps import AppConfig


class CertificatesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.certificates'
    verbose_name = '证书管理系统'
    
    def ready(self):
        import apps.certificates.signals
        self._ensure_ca_exists()

    def _ensure_ca_exists(self):
        import os
        if os.environ.get('RUN_MAIN') == 'true':
            return
        if os.environ.get('DJANGO_AUTORELOAD') == 'true':
            return
        try:
            CertificateAuthority = self.get_model('CertificateAuthority')
            if not CertificateAuthority.objects.filter(
                is_active=True
            ).exists():
                from utils.cert_service import generate_ca
                from cryptography.hazmat.primitives import serialization
                ca_key, ca_cert = generate_ca()
                ca = CertificateAuthority(name='WinRM-CA', is_active=True)
                ca.private_key = ca_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ).decode('utf-8')
                ca.certificate = (
                    ca_cert.public_bytes(serialization.Encoding.PEM)
                    .decode('utf-8')
                )
                import datetime
                ca.expires_at = (
                    datetime.datetime.now(datetime.timezone.utc)
                    + datetime.timedelta(days=3650)
                )
                ca.save()
        except Exception:
            pass