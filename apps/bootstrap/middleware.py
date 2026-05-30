import logging
from django.http import JsonResponse
from .models import ActiveSession
from django.utils import timezone
from django.urls import resolve

logger = logging.getLogger(__name__)


class SessionValidationMiddleware:
    """会话验证中间件 - 根据规范实现"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 记录请求信息用于调试
        client_ip = self.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', 'Unknown')
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        logger.debug(f"Session validation middleware processing request: path={request.path}, method={request.method}")
        
        # 检查是否需要验证会话的API端点
        # 仅对需要认证的API端点进行验证
        # 排除不需要SessionToken验证的特殊端点
        excluded_paths = [
            '/api/exchange_token', 
            '/api/exchange_token/',
            '/bootstrap/exchange-token/',
            '/api/get_session_token',
            '/api/get_session_token/',
            '/bootstrap/api/get_session_token',
            '/bootstrap/api/get_session_token/',
            '/api/check_totp_status',
            '/api/check_totp_status/',
            '/bootstrap/api/check_totp_status',
            '/bootstrap/api/check_totp_status/',
            '/bootstrap/sse/init-status',
            '/bootstrap/sse/init-status/',
            '/bootstrap/api/upload_host_cert',
            '/bootstrap/api/upload_host_cert/',
        ]
        
        if (request.path.startswith('/api/') or 
            request.path.startswith('/bootstrap/')) and \
           request.path not in excluded_paths:
            
            logger.debug(f"Checking session for protected endpoint: {request.path}")
            
            # 检查Authorization头部
            if auth_header.startswith('Bearer '):
                session_token = auth_header.split(' ')[1]
                logger.debug("Found Bearer token, validating session")
                
                # 验证会话有效性
                is_valid, result = self.check_session_validity(request, session_token)
                
                if not is_valid:
                    logger.warning(f"Session validation failed for request {request.path}: {result}")
                    return JsonResponse({
                        'success': False,
                        'error': 'Access denied',
                    }, status=403)
                else:
                    logger.debug("Session validation successful")
            else:
                logger.debug("No valid Bearer authorization header found")
        else:
            logger.debug(f"Skipping session validation for path: {request.path}")
        
        response = self.get_response(request)
        return response

    def check_session_validity(self, request, session_token):
        """检查会话有效性"""
        try:
            logger.debug(f"Looking up session token: {session_token[:8]}...")
            session = ActiveSession.objects.get(
                session_token=session_token,
                expires_at__gt=timezone.now()
            )
            
            logger.debug(f"Found active session for host: {session.host.name} (ID: {session.host.id})")
            
            # 获取真实客户端IP
            current_ip = self.get_client_ip(request)
            bound_ip = session.bound_ip
            
            logger.debug(f"Comparing IPs - Request IP: {current_ip}, Bound IP: {bound_ip}")
            
            # IP校验
            if session.bound_ip != current_ip:
                error_msg = f"IP address mismatch - request from {current_ip}, session bound to {bound_ip}"
                logger.warning(error_msg)
                logger.warning(f"Session details: token={session_token[:8]}..., host={session.host.name}, created={session.created_at}")
                return False, error_msg
            
            logger.debug(f"IP validation passed: {current_ip}")
            return True, session
            
        except ActiveSession.DoesNotExist:
            error_msg = f"Invalid or expired session token: {session_token[:8]}..."
            logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error during session validation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
    
    def get_client_ip(self, request):
        """获取客户端真实IP地址"""
        from django.conf import settings
        if getattr(settings, 'USE_X_FORWARDED_FOR', False):
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0].strip()
                logger.debug(f"Got IP from X-Forwarded-For: {ip}")
                return ip
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        logger.debug(f"Got IP from REMOTE_ADDR: {ip}")
        return ip