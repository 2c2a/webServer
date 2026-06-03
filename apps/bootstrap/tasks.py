import base64
import datetime
import logging
from datetime import timedelta
from typing import cast

from celery import shared_task
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.utils import timezone

from .models import ActiveSession, InitialToken

logger = logging.getLogger(__name__)


@shared_task
def cleanup_expired_sessions():
    try:
        expired_sessions = ActiveSession.objects.filter(
            expires_at__lt=timezone.now()
        )
        count = expired_sessions.count()
        expired_sessions.delete()
        logger.info(f"清理了 {count} 个过期的活动会话")
        return f"清理了 {count} 个过期的活动会话"
    except Exception as e:
        logger.error(f"清理过期会话时出错: {str(e)}")
        raise


@shared_task
def cleanup_expired_initial_tokens():
    try:
        cutoff_time = timezone.now() - timedelta(days=7)
        expired_tokens = InitialToken.objects.filter(
            expires_at__lt=cutoff_time
        )
        count = expired_tokens.count()
        expired_tokens.delete()
        logger.info(f"清理了 {count} 个过期的初始令牌")
        return f"清理了 {count} 个过期的初始令牌"
    except Exception as e:
        logger.error(f"清理过期初始令牌时出错: {str(e)}")
        raise


@shared_task
def generate_bootstrap_config(hostname, ip_address, operator_id):
    try:
        config = {
            'hostname': hostname,
            'ip_address': ip_address,
            'generated_at': timezone.now().isoformat(),
            'status': 'success',
        }
        return {'success': True, 'config': config}
    except Exception as e:
        logger.error(f"生成引导配置时出错: {str(e)}")
        return {'success': False, 'error': str(e)}


@shared_task
def initialize_host_bootstrap(host_id, operator_id):
    try:
        from apps.hosts.models import Host
        host = Host.objects.get(id=host_id)
        return {
            'host_id': host_id,
            'hostname': host.hostname,
            'status': 'completed',
            'completed_at': timezone.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"初始化主机引导时出错: {str(e)}")
        raise


@shared_task(bind=True, max_retries=1)
def cert_provision_issue_certs(self, token_str):
    from apps.bootstrap.models import CertProvisionToken
    from apps.certificates.models import CertificateAuthority
    from utils.cert_service import (
        issue_server_cert, issue_client_cert,
        generate_random_username, generate_random_password,
    )
    from utils.cert_storage import generate_cert_paths, save_cert_files

    try:
        provision_token = CertProvisionToken.objects.get(token=token_str)
    except CertProvisionToken.DoesNotExist:
        return

    if provision_token.status != 'HOSTNAME_UPLOADED':
        return

    host = provision_token.host
    hostname = host.hostname if host else provision_token.hostname
    if not hostname:
        return

    ip_address = provision_token.ip_address or ''

    ca_obj = CertificateAuthority.objects.filter(is_active=True).first()
    if not ca_obj:
        from utils.cert_service import generate_ca as _gen_ca

        ca_key, ca_cert = _gen_ca()
        ca_obj = CertificateAuthority(
            name='WinRM-CA', is_active=True,
        )
        ca_key_pem = ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        ca_cert_pem = ca_cert.public_bytes(
            serialization.Encoding.PEM,
        )
        ca_obj.save_ca_files(ca_key_pem, ca_cert_pem)
        ca_obj.expires_at = (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(days=3650)
        )
        ca_obj.save()

    ca_key_pem = ca_obj.private_key
    ca_cert_pem = ca_obj.certificate
    if not ca_key_pem or not ca_cert_pem:
        logger.error(
            f"CA {ca_obj.name} key/cert files not found on disk"
        )
        return

    ca_key = cast(
        ec.EllipticCurvePrivateKey,
        serialization.load_pem_private_key(
            ca_key_pem.encode(), password=None,
        ),
    )
    ca_cert = x509.load_pem_x509_certificate(ca_cert_pem.encode())

    ntlm_user = generate_random_username()
    ntlm_password = generate_random_password()
    upn_value = f"{ntlm_user}@localhost"

    server_result = issue_server_cert(
        ca_key=ca_key,
        ca_cert=ca_cert,
        hostname=hostname,
        ip_address=ip_address or None,
    )

    client_key, client_cert = issue_client_cert(
        ca_key=ca_key,
        ca_cert=ca_cert,
        upn_value=upn_value,
    )

    cert_root, cert_sub = generate_cert_paths()

    ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    client_cert_pem = client_cert.public_bytes(serialization.Encoding.PEM)
    client_key_pem = client_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    cert_dir = save_cert_files(
        cert_root=cert_root,
        cert_sub=cert_sub,
        ca_cert_pem=ca_cert_pem,
        client_cert_pem=client_cert_pem,
        server_pfx_bytes=server_result['pfx_data'],
        client_key_pem=client_key_pem,
    )

    if host:
        host.cert_root = cert_root
        host.cert_sub = cert_sub
        host.pfx_password = server_result['pfx_password']
        host.ntlm_fallback_user = ntlm_user
        host.ntlm_fallback_password = ntlm_password
        host.cert_provision_status = 'ready'
        host.cert_pem_path = str(cert_dir / 'client.crt')
        host.cert_key_path = str(cert_dir / 'client.key')
        host.auth_method = 'certificate'
        host.use_ssl = True
        if host.port == 5985:
            host.port = 5986
        host.save()

    if not host:
        provision_token.cert_data = {
            'cert_root': cert_root,
            'cert_sub': cert_sub,
            'pfx_password': server_result['pfx_password'],
            'ntlm_user': ntlm_user,
            'ntlm_password': ntlm_password,
            'ca_cert_b64': base64.b64encode(
                ca_cert_pem
            ).decode('utf-8'),
            'client_cert_b64': base64.b64encode(
                client_cert_pem
            ).decode('utf-8'),
            'server_pfx_b64': base64.b64encode(
                server_result['pfx_data']
            ).decode('utf-8'),
        }

    provision_token.status = 'CERT_ISSUED'
    provision_token.save()

    return {'success': True, 'host_id': host.pk if host else None}


@shared_task
def cleanup_expired_provision_tokens():
    from apps.bootstrap.models import CertProvisionToken
    now = timezone.now()
    CertProvisionToken.objects.filter(
        status='ISSUED', expires_at__lt=now,
    ).delete()
    week_ago = now - timedelta(days=7)
    CertProvisionToken.objects.filter(expires_at__lt=week_ago).delete()


@shared_task
def cleanup_unactivated_certificates():
    from apps.hosts.models import Host
    from utils.cert_storage import delete_cert_files
    now = timezone.now()
    cutoff = now - timedelta(minutes=60)
    hosts = Host.objects.filter(
        cert_provision_status__in=['pending', 'ready'],
        created_at__lt=cutoff,
        cert_activated_at__isnull=True,
    )
    for host in hosts:
        if host.cert_root and host.cert_sub:
            delete_cert_files(host.cert_root, host.cert_sub)
        host.cert_provision_status = 'failed'
        host.cert_root = ''
        host.cert_sub = ''
        host.save()


@shared_task
def cleanup_orphan_cert_dirs():
    from apps.hosts.models import Host
    from utils.cert_storage import get_cert_base_dir
    import shutil
    base_dir = get_cert_base_dir()
    if not base_dir.exists():
        return
    active_paths = set()
    for host in Host.objects.filter(cert_root__gt='', cert_sub__gt=''):
        active_paths.add((host.cert_root, host.cert_sub))
    for root_dir in base_dir.iterdir():
        if root_dir.is_dir() and len(root_dir.name) == 2:
            for sub_dir in root_dir.iterdir():
                if sub_dir.is_dir() and len(sub_dir.name) == 2:
                    if (root_dir.name, sub_dir.name) not in active_paths:
                        shutil.rmtree(sub_dir, ignore_errors=True)
            try:
                root_dir.rmdir()
            except OSError:
                logger.debug(
                    "Skipping removal of non-empty or inaccessible orphan cert root dir: %s",
                    root_dir,
                )
