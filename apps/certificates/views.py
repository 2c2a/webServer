from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required, permission_required
from .models import ServerCertificate, CertificateAuthority, ClientCertificate
from apps.hosts.models import Host
from django.utils.decorators import method_decorator
from django.views import View
from django.shortcuts import get_object_or_404
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@login_required
@permission_required('certificates.add_servercertificate', raise_exception=True)
def issue_server_certificate(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        hostname = data.get('hostname')
        san_names = data.get('san_names', [])
        ca_name = data.get('ca_name', 'default-ca')

        if not hostname:
            return JsonResponse({
                'success': False,
                'error': 'Hostname is required'
            }, status=400)

        ca, created = CertificateAuthority.objects.get_or_create(
            name=ca_name,
            defaults={
                'name': ca_name,
                'description': f'Default CA for {ca_name}'
            }
        )
        if created:
            ca.generate_self_signed_cert()
            ca.save()
            logger.info(f"Created new CA: {ca_name}")

        cert, created = ServerCertificate.objects.get_or_create(
            hostname=hostname,
            defaults={
                'hostname': hostname,
                'ca': ca
            }
        )

        if created or cert.is_revoked:
            from utils.cert_service import (
                issue_server_cert, generate_ca,
            )
            from cryptography.hazmat.primitives import serialization
            from cryptography import x509 as x509_mod
            from typing import cast
            from cryptography.hazmat.primitives.asymmetric import ec

            ca_key = cast(
                ec.EllipticCurvePrivateKey,
                serialization.load_pem_private_key(
                    ca.private_key.encode(), password=None,
                ),
            )
            ca_cert = x509_mod.load_pem_x509_certificate(
                ca.certificate.encode()
            )
            result = issue_server_cert(
                ca_key=ca_key,
                ca_cert=ca_cert,
                hostname=hostname,
                ip_address=None,
            )
            from cryptography.hazmat.primitives import hashes
            fingerprint = result['server_cert'].fingerprint(
                hashes.SHA1()
            )
            cert.thumbprint = ":".join(
                f"{byte:02X}" for byte in fingerprint
            )
            cert.is_revoked = False
            cert.expires_at = (
                datetime.utcnow() + __import__('datetime').timedelta(
                    days=3650
                )
            )
            cert.save()
            logger.info(f"Issued new server certificate for {hostname}")
        elif cert.expires_at and cert.expires_at < datetime.utcnow():
            cert.is_revoked = True
            cert.save()
            logger.info(f"Marked expired server cert for {hostname}")

        return JsonResponse({
            'success': True,
            'data': {
                'thumbprint': cert.thumbprint,
                'expires_at': (
                    cert.expires_at.isoformat() if cert.expires_at else None
                )
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error issuing server certificate: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to issue server certificate'
        }, status=500)


@require_http_methods(["POST"])
@login_required
@permission_required('certificates.add_clientcertificate', raise_exception=True)
def issue_client_certificate(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        name = data.get('name')
        user_id = data.get('user_id')
        description = data.get('description', '')
        ca_name = data.get('ca_name', 'default-ca')

        if not name:
            return JsonResponse({
                'success': False,
                'error': 'Certificate name is required'
            }, status=400)

        ca, created = CertificateAuthority.objects.get_or_create(
            name=ca_name,
            defaults={
                'name': ca_name,
                'description': f'Default CA for {ca_name}'
            }
        )
        if created:
            ca.generate_self_signed_cert()
            ca.save()

        user = None
        if user_id:
            from django.contrib.auth.models import User
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'User not found'
                }, status=404)

        cert, created = ClientCertificate.objects.get_or_create(
            name=name,
            defaults={
                'name': name,
                'ca': ca,
                'assigned_to_user': user,
                'description': description
            }
        )

        if created:
            from utils.cert_service import issue_client_cert
            from cryptography.hazmat.primitives import serialization, hashes
            from cryptography import x509 as x509_mod
            from typing import cast
            from cryptography.hazmat.primitives.asymmetric import ec

            ca_key = cast(
                ec.EllipticCurvePrivateKey,
                serialization.load_pem_private_key(
                    ca.private_key.encode(), password=None,
                ),
            )
            ca_cert = x509_mod.load_pem_x509_certificate(
                ca.certificate.encode()
            )
            upn_value = f"{name}@localhost"
            cert.upn_value = upn_value
            client_key, client_cert = issue_client_cert(
                ca_key=ca_key,
                ca_cert=ca_cert,
                upn_value=upn_value,
            )
            fingerprint = client_cert.fingerprint(hashes.SHA1())
            cert.thumbprint = ":".join(
                f"{byte:02X}" for byte in fingerprint
            )
            cert.expires_at = (
                datetime.utcnow() + __import__('datetime').timedelta(
                    days=3650
                )
            )
            cert.save()
            logger.info(f"Issued new client certificate for {name}")

        return JsonResponse({
            'success': True,
            'data': {
                'thumbprint': cert.thumbprint,
                'expires_at': (
                    cert.expires_at.isoformat() if cert.expires_at else None
                )
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(
            f"Error issuing client certificate: {str(e)}", exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': 'Failed to issue client certificate'
        }, status=500)


@require_http_methods(["POST"])
@login_required
def validate_certificate_request(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        hostname = data.get('hostname')
        token = data.get('token')

        if not hostname or not token:
            return JsonResponse({
                'success': False,
                'error': 'Hostname and token are required'
            }, status=400)

        host = Host.objects.filter(
            hostname=hostname,
        ).first()

        if not host:
            return JsonResponse({
                'success': False,
                'error': 'Invalid or expired token'
            }, status=401)

        return JsonResponse({
            'success': True,
            'data': {
                'hostname': hostname,
                'host_id': host.id,
                'valid': True
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(
            f"Error validating certificate request: {str(e)}", exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': 'Certificate validation failed'
        }, status=500)


@require_http_methods(["GET"])
@login_required
def get_ca_certificate(request):
    try:
        ca_name = request.GET.get('ca_name', 'default-ca')

        try:
            ca = CertificateAuthority.objects.get(
                name=ca_name, is_active=True
            )
            return JsonResponse({
                'success': True,
                'data': {
                    'ca_cert': ca.certificate,
                    'expires_at': ca.expires_at.isoformat()
                }
            })
        except CertificateAuthority.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'CA not found or not active'
            }, status=404)

    except Exception as e:
        logger.error(
            f"Error getting CA certificate: {str(e)}", exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve CA certificate'
        }, status=500)


class CertificateManagementView(View):

    @method_decorator(
        permission_required('certificates.view_certificateauthority')
    )
    def get(self, request):
        try:
            cert_type = request.GET.get('type', 'all')

            result = {'success': True, 'data': {}}

            if cert_type in ['all', 'ca']:
                cas = CertificateAuthority.objects.all()
                result['data']['cas'] = [
                    {
                        'id': ca.id,
                        'name': ca.name,
                        'created_at': ca.created_at.isoformat(),
                        'expires_at': ca.expires_at.isoformat(),
                        'is_active': ca.is_active
                    }
                    for ca in cas
                ]

            if cert_type in ['all', 'server']:
                servers = ServerCertificate.objects.select_related('ca').all()
                result['data']['servers'] = [
                    {
                        'id': cert.id,
                        'hostname': cert.hostname,
                        'ca_name': cert.ca.name,
                        'thumbprint': cert.thumbprint,
                        'created_at': cert.created_at.isoformat(),
                        'expires_at': cert.expires_at.isoformat(),
                        'is_revoked': cert.is_revoked
                    }
                    for cert in servers
                ]

            if cert_type in ['all', 'client']:
                clients = ClientCertificate.objects.select_related(
                    'ca', 'assigned_to_user'
                ).all()
                result['data']['clients'] = [
                    {
                        'id': cert.id,
                        'name': cert.name,
                        'ca_name': cert.ca.name,
                        'assigned_to_user': (
                            cert.assigned_to_user.username
                            if cert.assigned_to_user else None
                        ),
                        'thumbprint': cert.thumbprint,
                        'created_at': cert.created_at.isoformat(),
                        'expires_at': cert.expires_at.isoformat(),
                        'is_active': cert.is_active
                    }
                    for cert in clients
                ]

            return JsonResponse(result)

        except Exception as e:
            logger.error(
                f"Error getting certificates: {str(e)}", exc_info=True
            )
            return JsonResponse({
                'success': False,
                'error': 'Failed to retrieve certificates'
            }, status=500)

    @method_decorator(
        permission_required('certificates.delete_servercertificate')
    )
    def delete(self, request):
        try:
            cert_id = request.GET.get('id')
            cert_type = request.GET.get('type', 'server')

            if not cert_id:
                return JsonResponse({
                    'success': False,
                    'error': 'Certificate ID is required'
                }, status=400)

            if cert_type == 'server':
                cert = get_object_or_404(ServerCertificate, id=cert_id)
                cert.revoke("Revoked by admin")
            elif cert_type == 'client':
                cert = get_object_or_404(ClientCertificate, id=cert_id)
                cert.is_active = False
                cert.save()
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid certificate type'
                }, status=400)

            return JsonResponse({
                'success': True,
                'message': (
                    f'{cert_type.title()} certificate revoked successfully'
                )
            })

        except Exception as e:
            logger.error(
                f"Error revoking certificate: {str(e)}", exc_info=True
            )
            return JsonResponse({
                'success': False,
                'error': 'Failed to revoke certificate'
            }, status=500)


@require_http_methods(["POST"])
@login_required
@permission_required(
    'certificates.change_servercertificate', raise_exception=True
)
def renew_certificate(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
        cert_id = data.get('cert_id')
        cert_type = data.get('type', 'server')

        if not cert_id:
            return JsonResponse({
                'success': False,
                'error': 'Certificate ID is required'
            }, status=400)

        if cert_type == 'server':
            cert = get_object_or_404(ServerCertificate, id=cert_id)
            cert.is_revoked = False
            cert.save()
        elif cert_type == 'client':
            cert = get_object_or_404(ClientCertificate, id=cert_id)
            cert.is_active = True
            cert.save()
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid certificate type'
            }, status=400)

        return JsonResponse({
            'success': True,
            'message': f'{cert_type.title()} certificate renewed successfully',
            'data': {
                'expires_at': (
                    cert.expires_at.isoformat() if cert.expires_at else None
                )
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(
            f"Error renewing certificate: {str(e)}", exc_info=True
        )
        return JsonResponse({
            'success': False,
            'error': 'Failed to renew certificate'
        }, status=500)
