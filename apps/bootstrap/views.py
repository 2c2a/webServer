from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator
from django.views import View
from .models import InitialToken, ActiveSession
from apps.hosts.models import Host
from apps.certificates.models import CertificateAuthority, ServerCertificate
from apps.tasks.models import AsyncTask
from apps.bootstrap.tasks import generate_bootstrap_config, initialize_host_bootstrap
from django.shortcuts import get_object_or_404
import json
import logging
from django.utils import timezone
from django.core.cache import cache
import secrets
import uuid
import time
import hmac

from utils.helpers import get_client_ip


logger = logging.getLogger(__name__)


def _bootstrap_rate_limit(key_prefix, rate='10/m'):
    limit, period = rate.lower().split('/')
    limit = int(limit)
    period_map = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    period_seconds = period_map.get(period, 60)

    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            window = int(time.time() // period_seconds)
            cache_key = f'rl:{key_prefix}:{ip}:{window}'
            current = cache.get(cache_key, 0)
            if current >= limit:
                return JsonResponse(
                    {'success': False, 'error': 'Too many requests'},
                    status=429,
                )
            cache.set(cache_key, current + 1, timeout=period_seconds + 1)
            return view_func(request, *args, **kwargs)
        wrapper.__name__ = view_func.__name__
        return wrapper
    return decorator


@csrf_exempt
@require_http_methods(["POST"])
def _save_cert_to_host(host, pfx_b64, pfx_password, service_user, service_password):
    import base64
    from cryptography.hazmat.primitives.serialization import pkcs12, Encoding, PrivateFormat, NoEncryption

    try:
        pfx_data = base64.b64decode(pfx_b64)
        private_key, certificate, _ = pkcs12.load_key_and_certificates(
            pfx_data, pfx_password.encode()
        )
    except Exception as e:
        logger.error(f"PFX decode failed for host {host.pk}: {e}")
        return False

    if not private_key or not certificate:
        return False

    import os
    from django.conf import settings
    cert_dir = os.path.join(settings.MEDIA_ROOT, 'certs', 'hosts', str(host.pk))
    os.makedirs(cert_dir, exist_ok=True)

    pem_path = os.path.join(cert_dir, 'client.pem')
    key_path = os.path.join(cert_dir, 'client.key')

    with open(pem_path, 'wb') as f:
        f.write(certificate.public_bytes(Encoding.PEM))
    with open(key_path, 'wb') as f:
        f.write(private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))

    os.chmod(pem_path, 0o600)
    os.chmod(key_path, 0o600)

    update_fields = {'cert_pem_path': pem_path, 'cert_key_path': key_path}
    if service_user and service_password:
        update_fields['username'] = service_user
        from utils.crypto import encrypt_value
        update_fields['password'] = encrypt_value(service_password)

    from apps.hosts.models import Host
    Host.objects.filter(pk=host.pk).update(**update_fields)

    try:
        host.refresh_from_db()
        host.test_connection()
    except Exception as e:
        logger.warning(f"Connection test after cert upload failed: {e}")

    return True


def upload_host_cert(request):
    try:
        data = json.loads(request.body)
        token_value = data.get('token', '')
        pfx_b64 = data.get('pfx_b64', '')
        pfx_password = data.get('pfx_password', '')
        service_user = data.get('service_user', '')
        service_password = data.get('service_password', '')

        if not token_value or not pfx_b64:
            return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)

        try:
            token_obj = InitialToken.objects.get(token=token_value)
        except InitialToken.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Invalid token'}, status=401)

        if token_obj.host:
            ok = _save_cert_to_host(
                token_obj.host, pfx_b64, pfx_password,
                service_user, service_password,
            )
            if not ok:
                return JsonResponse({'success': False, 'error': 'Invalid PFX data'}, status=400)
        else:
            token_obj.cert_data = {
                'pfx_b64': pfx_b64,
                'pfx_password': pfx_password,
                'service_user': service_user,
                'service_password': service_password,
            }
            token_obj.save(update_fields=['cert_data'])
            logger.info(f"Cert data stored on token {token_obj.pk[:8]}, waiting for host association")

        logger.info(f"Cert uploaded for token {token_obj.pk[:8]}")
        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"upload_host_cert error: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@permission_required('hosts.delete_host', raise_exception=True)
def revoke_pending_host(request):
    """
    吊销待验证主机
    删除InitialToken和关联的Host记录
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        token = data.get('token')
        
        if not token:
            return JsonResponse({
                'success': False,
                'error': 'Token is required'
            }, status=400)
        
        try:
            initial_token = InitialToken.objects.get(token=token)
            host = initial_token.host
            
            initial_token.delete()
            host.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Host revoked successfully'
            })
            
        except InitialToken.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Token not found'
            }, status=404)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error revoking pending host: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to revoke pending host'
        }, status=500)


@require_http_methods(["GET"])
@login_required
@permission_required('bootstrap.view_initialtoken', raise_exception=True)
def get_pending_hosts(request):
    """
    获取待验证的主机列表
    返回所有状态为ISSUED的InitialToken
    """
    try:
        from apps.hosts.models import Host
        
        current_time = timezone.now()
        pending_tokens = InitialToken.objects.filter(
            status='ISSUED',
            expires_at__gt=current_time
        ).select_related('host').order_by('-created_at')
        
        hosts = []
        for token in pending_tokens:
            if token.host:
                hosts.append({
                    'token': token.token,
                    'hostname': token.host.hostname,
                    'host_id': token.host.id,
                    'created_at': token.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'expires_at': token.expires_at.strftime('%Y-%m-%d %H:%M:%S')
                })
        
        return JsonResponse({
            'success': True,
            'data': {
                'hosts': hosts
            }
        })
        
    except Exception as e:
        logger.error(f"Error in get_pending_hosts: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to get pending hosts'
        }, status=500)


@require_http_methods(["POST"])
@login_required
@permission_required('bootstrap.add_initialtoken', raise_exception=True)
def create_initial_token(request):
    """创建初始令牌API - 基于配对码的简化认证机制"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        host_id = data.get('host_id')
        operator_id = data.get('operator_id')
        expire_hours = data.get('expire_hours', 24)

        if not host_id:
            return JsonResponse({
                'success': False,
                'error': 'Host ID is required'
            }, status=400)

        if not operator_id:
            return JsonResponse({
                'success': False,
                'error': 'Operator ID is required'
            }, status=400)

        try:
            host = Host.objects.get(id=host_id)
        except Host.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Host not found'
            }, status=404)

        from datetime import timedelta
        from django.utils import timezone

        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(hours=expire_hours)

        initial_token = InitialToken.objects.create(
            token=token,
            host=host,
            expires_at=expires_at,
            status='ISSUED'
        )

        pairing_code = initial_token.generate_pairing_code()

        import base64
        config_data = {
            'c_side_url': request.build_absolute_uri('/').rstrip('/'),
            'token': initial_token.token,
            'host_id': str(host.id),
            'expires_at': initial_token.expires_at.isoformat()
        }

        config_json = json.dumps(config_data)
        encoded_config = base64.b64encode(config_json.encode('utf-8')).decode('utf-8')

        return JsonResponse({
            'success': True,
            'data': {
                'token': initial_token.token,
                'expires_at': initial_token.expires_at.isoformat(),
                'host_id': host.id,
                'hostname': host.hostname,
                'pairing_code': pairing_code,
                'encoded_config': encoded_config
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error creating initial token: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to create initial token'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@_bootstrap_rate_limit('pairing_verify', '5/m')
def verify_pairing_code(request):
    """配对码验证接口 - 简化的认证机制
    
    支持两种参数方式：
    1. 通过 host_id 和 pairing_code 验证
    2. 通过 token 和 pairing_code 验证
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        host_id = data.get('host_id')
        token = data.get('token')
        pairing_code = data.get('pairing_code')
        
        if not pairing_code:
            return JsonResponse({
                'success': False,
                'error': 'Pairing code is required'
            }, status=400)
        
        if not host_id and not token:
            return JsonResponse({
                'success': False,
                'error': 'Either host_id or token is required'
            }, status=400)
        
        try:
            if token:
                try:
                    token_obj = InitialToken.objects.get(
                        token=token,
                        status='ISSUED',
                        expires_at__gt=timezone.now()
                    )
                    
                    if token_obj.verify_pairing_code(pairing_code):
                        return JsonResponse({
                            'success': True,
                            'message': 'Pairing code verification successful'
                        })
                    else:
                        return JsonResponse({
                            'success': False,
                            'error': 'Invalid or expired pairing code'
                        }, status=400)
                        
                except InitialToken.DoesNotExist:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid request'
                    }, status=400)
            else:
                initial_tokens = InitialToken.objects.filter(
                    host_id=host_id,
                    status='ISSUED',
                    expires_at__gt=timezone.now()
                )
                
                if not initial_tokens.exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid request'
                    }, status=400)
                
                verified = False
                for token_obj in initial_tokens:
                    if token_obj.verify_pairing_code(pairing_code):
                        verified = True
                        break
                
                if verified:
                    return JsonResponse({
                        'success': True,
                        'message': 'Pairing code verification successful'
                    })
                else:
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid or expired pairing code'
                    }, status=400)
                
        except Exception as e:
            logger.error(f"Error verifying pairing code: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Pairing code verification failed'
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error validating pairing code: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Pairing code validation failed'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def get_bootstrap_config(request):
    """获取主机引导配置API"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        hostname = data.get('hostname')
        ip_address = data.get('ip_address')
        auth_token = data.get('auth_token')  # 认证令牌
        
        if not hostname or not auth_token:
            return JsonResponse({
                'success': False,
                'error': 'Hostname and auth_token are required'
            }, status=400)
        
        # 验证初始令牌
        try:
            token_obj = InitialToken.objects.get(
                token=auth_token,
                status='PAIRED',  # 确保已经配对验证
                expires_at__gt=timezone.now()
            )
        except InitialToken.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid or unauthorized bootstrap token'
            }, status=401)
        
        # 验证主机是否匹配令牌
        if str(token_obj.host.id) != data.get('host_id', ''):
            return JsonResponse({
                'success': False,
                'error': 'Host ID does not match the token'
            }, status=400)
        
        # 标记令牌为已使用
        token_obj.status = 'CONSUMED'
        token_obj.save()
        
        # 生成活动会话
        session_token = str(uuid.uuid4())
        bound_ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        
        ActiveSession.objects.create(
            session_token=session_token,
            host=token_obj.host,
            bound_ip=bound_ip,
            expires_at=timezone.now() + timezone.timedelta(days=1)  # 24小时有效期
        )
        
        # 生成引导配置（异步任务）
        from apps.accounts.models import User
        admin_user = User.objects.filter(is_superuser=True).first()
        operator_id = admin_user.id if admin_user else None
        
        task_result = generate_bootstrap_config.delay(
            hostname=hostname,
            ip_address=ip_address or token_obj.host.ip_address,
            operator_id=operator_id
        )
        
        # 等待任务完成（最多等待30秒）
        config_result = task_result.get(timeout=30)
        
        if config_result['success']:
            return JsonResponse({
                'success': True,
                'data': config_result['config'],
                'session_token': session_token  # 返回新的会话令牌
            })
        else:
            return JsonResponse({
                'success': False,
                'error': config_result.get('error', 'Failed to generate bootstrap config')
            }, status=500)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error getting bootstrap config: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to get bootstrap config'
        }, status=500)


@require_http_methods(["POST"])
@login_required
@permission_required('bootstrap.change_initialtoken', raise_exception=True)
def trigger_host_bootstrap(request):
    """触发主机引导流程API"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        host_id = data.get('host_id')
        operator_id = data.get('operator_id')

        if not host_id:
            return JsonResponse({
                'success': False,
                'error': 'Host ID is required'
            }, status=400)

        if not operator_id:
            return JsonResponse({
                'success': False,
                'error': 'Operator ID is required'
            }, status=400)

        try:
            host = Host.objects.get(id=host_id)
        except Host.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Host not found'
            }, status=404)

        task_result = initialize_host_bootstrap.delay(
            host_id=host_id,
            operator_id=operator_id
        )

        return JsonResponse({
            'success': True,
            'data': {
                'task_id': task_result.id,
                'host_id': host_id,
                'hostname': host.hostname,
                'status': 'started'
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error triggering host bootstrap: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to trigger host bootstrap'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@_bootstrap_rate_limit('bootstrap_status', '10/m')
def check_bootstrap_status(request):
    """检查引导状态API"""
    try:
        token = request.GET.get('token')
        host_id = request.GET.get('host_id')
        
        if not token and not host_id:
            return JsonResponse({
                'success': False,
                'error': 'Either token or host_id is required'
            }, status=400)
        
        if token:
            try:
                initial_token = InitialToken.objects.get(token=token)
                host = initial_token.host
            except InitialToken.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid token'
                }, status=404)
        else:
            try:
                host = Host.objects.get(id=host_id)
            except Host.DoesNotExist:
                return JsonResponse({
                    'success': False,
                    'error': 'Host not found'
                }, status=404)
        
        return JsonResponse({
            'success': True,
            'data': {
                'host_id': host.id,
                'hostname': host.hostname,
                'init_status': host.init_status if hasattr(host, 'init_status') else 'unknown',
                'initialized_at': getattr(host, 'initialized_at', None),
            }
        })
        
    except Exception as e:
        logger.error(f"Error checking bootstrap status: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to check bootstrap status'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@_bootstrap_rate_limit('token_validate', '10/m')
def validate_bootstrap_token(request):
    """验证引导令牌有效性"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        token = data.get('token')
        
        if not token:
            return JsonResponse({
                'success': False,
                'error': 'Token is required'
            }, status=400)
        
        try:
            token_obj = InitialToken.objects.get(
                token=token,
                status__in=['ISSUED', 'PAIRED'],
                expires_at__gt=timezone.now()
            )
            
            return JsonResponse({
                'success': True,
                'data': {
                    'valid': True,
                    'expires_at': token_obj.expires_at.isoformat(),
                    'status': token_obj.status
                }
            })
        except InitialToken.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid or expired token'
            }, status=401)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error validating bootstrap token: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Token validation failed'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@_bootstrap_rate_limit('session_token', '10/m')
def get_session_token(request):
    """获取会话令牌接口 - H端初始化流程的第一步"""
    try:
        client_ip = get_client_ip(request)
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header.startswith('Bearer '):
            return JsonResponse({
                'success': False,
                'error': 'Authorization header missing or invalid'
            }, status=401)
        
        initial_token = auth_header.split(' ')[1]
        
        try:
            token_obj = InitialToken.objects.get(
                token=initial_token,
                status__in=['ISSUED', 'PAIRED'],
                expires_at__gt=timezone.now()
            )
        except InitialToken.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid or expired initial token'
            }, status=401)
        
        # 获取真实客户端IP
        ip = client_ip
        
        # 原子操作：生成新的session_token，创建ActiveSession记录
        from django.db import transaction
        with transaction.atomic():
            session_token = str(uuid.uuid4())

            if token_obj.host:
                ActiveSession.objects.create(
                    session_token=session_token,
                    host=token_obj.host,
                    bound_ip=ip,
                    expires_at=timezone.now() + timezone.timedelta(hours=1)
                )

            token_obj.status = 'CONSUMED'
            token_obj.save()
        
        return JsonResponse({
            'success': True,
            'session_token': session_token,
            'expires_in': 3600,
        })
        
    except Exception as e:
        logger.error(f"Error creating session token: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to create session token'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@_bootstrap_rate_limit('exchange_token', '10/m')
def exchange_token(request):
    """令牌交换接口 - 根据规范"""
    try:
        client_ip = get_client_ip(request)
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if not auth_header.startswith('Bearer '):
            return JsonResponse({
                'success': False,
                'error': 'Authorization header missing or invalid'
            }, status=401)
        
        session_token = auth_header.split(' ')[1]
        
        try:
            active_session = ActiveSession.objects.get(
                session_token=session_token,
                expires_at__gt=timezone.now()
            )
        except ActiveSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid or expired session token'
            }, status=401)
        
        # 验证IP绑定
        current_ip = client_ip
        if active_session.bound_ip != current_ip:
            return JsonResponse({
                'success': False,
                'error': 'IP address mismatch'
            }, status=403)
        
        # 延长会话有效期
        from django.db import transaction
        with transaction.atomic():
            active_session.expires_at = timezone.now() + timezone.timedelta(days=7)  # 延长到7天
            active_session.save()
        
        return JsonResponse({
            'success': True,
            'session_token': session_token,
            'expires_in': 604800,
        })
        
    except Exception as e:
        logger.error(f"Error exchanging token: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Token exchange failed'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@_bootstrap_rate_limit('pairing_status', '10/m')
def check_pairing_status(request):
    """检查配对状态接口"""
    try:
        # 从Authorization头获取InitialToken
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({
                'paired': False,
                'message': 'Invalid authorization header'
            }, status=401)
        
        initial_token = auth_header.split(' ')[1]
        
        # 查找对应的初始令牌
        try:
            token_obj = InitialToken.objects.get(
                token=initial_token,
                expires_at__gt=timezone.now()
            )
            
            if token_obj.status == 'PAIRED':
                return JsonResponse({
                    'paired': True,
                    'message': 'Pairing completed',
                })
            elif token_obj.status == 'ISSUED':
                return JsonResponse({
                    'paired': False,
                    'message': 'Waiting for pairing code verification',
                })
            elif token_obj.status == 'CONSUMED':
                return JsonResponse({
                    'paired': True,
                    'message': 'Token already consumed',
                })
            else:
                return JsonResponse({
                    'paired': False,
                    'message': f'Token status: {token_obj.status}'
                })
                
        except InitialToken.DoesNotExist:
            return JsonResponse({
                'paired': False,
                'message': 'Invalid or expired token'
            }, status=404)
            
    except Exception as e:
        logger.error(f"Error checking pairing status: {str(e)}", exc_info=True)
        return JsonResponse({
            'paired': False,
            'message': 'Internal error'
        }, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def revoke_session(request):
    """吊销会话接口 - 根据规范"""
    try:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({
                'success': False,
                'error': 'Authorization header missing or invalid'
            }, status=401)
        
        session_token = auth_header.split(' ')[1]
        
        # 删除ActiveSession表中的对应记录
        try:
            session = ActiveSession.objects.get(session_token=session_token)
            session.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Session revoked successfully'
            })
        except ActiveSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Invalid session token'
            }, status=401)
        
    except Exception as e:
        logger.error(f"Error revoking session: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to revoke session'
        }, status=500)


@require_http_methods(["POST"])
@login_required
@permission_required('hosts.add_host', raise_exception=True)
def complete_auto_register(request):
    """
    完成自动注册
    h_side_init.exe验证成功后调用此API创建主机记录
    """
    try:
        import json
        from apps.hosts.models import Host
        
        data = json.loads(request.body.decode('utf-8'))
        
        token = data.get('token', '')
        hostname = data.get('hostname', '')
        
        if not token or not hostname:
            return JsonResponse({
                'success': False,
                'error': 'token and hostname are required'
            }, status=400)
        
        # 检查是否已存在同名主机
        existing_host = Host.objects.filter(hostname=hostname).first()
        if existing_host:
            host = existing_host
            host.status = 'offline'
            host.save()
            logger.info(f"主机 {hostname} 已存在，更新状态")
        else:
            # 创建新主机
            host = Host.objects.create(
                name=hostname,
                hostname=hostname,
                connection_type='tunnel',
                username='placeholder',
                password='placeholder',
                status='offline',
                description='自动注册主机'
            )
            logger.info(f"自动创建新主机: {hostname}")
        
        # 创建InitialToken
        from datetime import timedelta
        import secrets
        
        expires_at = timezone.now() + timedelta(hours=24)
        initial_token = InitialToken.objects.create(
            token=token,
            host=host,
            expires_at=expires_at,
            status='ISSUED'
        )
        
        # 生成配对码
        pairing_code = initial_token.generate_pairing_code()
        
        return JsonResponse({
            'success': True,
            'data': {
                'host_id': host.id,
                'hostname': host.hostname,
                'pairing_code': pairing_code,
                'token': initial_token.token
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in complete_auto_register: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to complete auto register'
        }, status=500)


@require_http_methods(["POST"])
@login_required
@permission_required('hosts.add_host', raise_exception=True)
def auto_register_host(request):
    """
    自动注册主机接口
    只生成预注册token，不创建主机记录
    主机记录在h_side_init.exe完成验证后创建
    """
    try:
        import json
        import secrets
        from datetime import timedelta
        
        data = json.loads(request.body.decode('utf-8'))
        hostname = data.get('hostname', '')
        
        # 验证必填字段
        if not hostname:
            return JsonResponse({
                'success': False,
                'error': 'hostname is required'
            }, status=400)
        
        # 生成预注册token（不创建主机记录）
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(hours=24)
        
        # 构建配置数据（供h_side_init.exe使用）
        current_site = request.build_absolute_uri('/').rstrip('/')
        secret_data = {
            "c_side_url": current_site,
            "token": token,
            "hostname": hostname,
            "generated_at": timezone.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "auto_register": True  # 标记为自动注册模式
        }
        
        import base64
        json_str = json.dumps(secret_data, ensure_ascii=False)
        encoded_bytes = base64.b64encode(json_str.encode('utf-8'))
        encoded_str = encoded_bytes.decode('utf-8')
        
        # 生成 PowerShell 脚本（下载并运行）
        download_url = "https://2c2a.cc.cd/2c2a/HostInitBash/releases/latest/download/h_side_init.exe"
        script = f'''$exe = "$env:TEMP\\h_side_init.exe"
Invoke-WebRequest -Uri "{download_url}" -OutFile $exe -UseBasicParsing
& $exe "{encoded_str}"'''
        
        return JsonResponse({
            'success': True,
            'data': {
                'script': script,
                'secret': encoded_str
            }
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in auto_register_host: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to generate register script'
        }, status=500)


@login_required
def sse_init_status(request):
    import json as _json

    token = request.GET.get('token', '')
    if not token:
        return JsonResponse(
            {'error': 'token required'}, status=400,
        )

    def event_stream():
        for _ in range(120):
            try:
                token_obj = InitialToken.objects.get(token=token)
                status = token_obj.status
                data = {
                    'status': status,
                    'host_id': (
                        token_obj.host_id
                        if token_obj.host_id else None
                    ),
                }
                if status == 'CONSUMED' and token_obj.host:
                    host_status = Host.objects.filter(
                        pk=token_obj.host_id
                    ).values_list('status', flat=True).first()
                    data['host_status'] = host_status
                    if host_status == 'online':
                        yield f"data: {_json.dumps(data)}\n\n"
                        return
                yield f"data: {_json.dumps(data)}\n\n"
                if status == 'CONSUMED':
                    for _ in range(24):
                        time.sleep(5)
                        host_status = Host.objects.filter(
                            pk=token_obj.host_id
                        ).values_list('status', flat=True).first()
                        if host_status == 'online':
                            data['host_status'] = host_status
                            yield f"data: {_json.dumps(data)}\n\n"
                            return
                    return
            except InitialToken.DoesNotExist:
                yield f"data: {_json.dumps({'status': 'NOT_FOUND'})}\n\n"
                return
            time.sleep(5)
        yield f"data: {_json.dumps({'status': 'TIMEOUT'})}\n\n"

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def get_client_ip(request):
    """获取客户端真实IP地址"""
    from django.conf import settings as django_settings
    if getattr(django_settings, 'USE_X_FORWARDED_FOR', False):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '127.0.0.1')


class BootstrapManagementView(View):
    """引导管理视图 - 需要管理员权限"""
    
    @method_decorator(permission_required('bootstrap.view_initialtoken'))
    def get(self, request):
        """获取引导令牌列表"""
        try:
            page = int(request.GET.get('page', 1))
            page_size = min(int(request.GET.get('page_size', 20)), 100)  # 最大100条每页
            status_filter = request.GET.get('status')  # issued, paired, consumed, all
            
            queryset = InitialToken.objects.select_related('host').all()
            
            # 状态过滤
            if status_filter == 'issued':
                queryset = queryset.filter(status='ISSUED')
            elif status_filter == 'paired':
                queryset = queryset.filter(status='PAIRED')
            elif status_filter == 'consumed':
                queryset = queryset.filter(status='CONSUMED')
            elif status_filter == 'expired':
                queryset = queryset.filter(expires_at__lt=timezone.now())
            elif status_filter != 'all':
                # 默认显示未过期的
                queryset = queryset.filter(expires_at__gt=timezone.now())
            
            # 分页
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            tokens = queryset[start_idx:end_idx]
            
            total_count = queryset.count()
            
            result = {
                'success': True,
                'data': {
                    'tokens': [
                        {
                            'id': token.token,
                            'token': token.token,
                            'hostname': token.host.hostname,
                            'host_id': token.host.id,
                            'created_at': token.created_at.isoformat(),
                            'expires_at': token.expires_at.isoformat(),
                            'status': token.status,
                            'is_expired': token.expires_at < timezone.now()
                        }
                        for token in tokens
                    ],
                    'pagination': {
                        'page': page,
                        'page_size': page_size,
                        'total_count': total_count,
                        'total_pages': (total_count + page_size - 1) // page_size
                    }
                }
            }
            
            return JsonResponse(result)
            
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid page or page_size parameter'
            }, status=400)
        except Exception as e:
            logger.error(f"Error getting bootstrap tokens: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to retrieve bootstrap tokens'
            }, status=500)
    
    @method_decorator(permission_required('bootstrap.delete_initialtoken'))
    def delete(self, request):
        """删除引导令牌"""
        try:
            token_id = request.GET.get('id')
            
            if not token_id:
                return JsonResponse({
                    'success': False,
                    'error': 'Token ID is required'
                }, status=400)
            
            token = get_object_or_404(InitialToken, token=token_id)
            token.delete()
            
            return JsonResponse({
                'success': True,
                'message': 'Initial token deleted successfully'
            })
            
        except Exception as e:
            logger.error(f"Error deleting initial token: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to delete initial token'
            }, status=500)