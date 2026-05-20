from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.decorators import method_decorator
from django.views import View
from .models import AuditLog, SensitiveOperation, SecurityEvent, SessionActivity
from apps.hosts.models import Host
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.core.paginator import Paginator
from django.utils import timezone
from datetime import datetime, timedelta
import json
import logging
import re

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 100
MAX_SEARCH_LENGTH = 200
DATE_FORMAT = '%Y-%m-%d'


def _validate_int_param(value, default=1, min_val=1, max_val=None):
    try:
        result = int(value)
        result = max(min_val, result)
        if max_val:
            result = min(max_val, result)
        return result
    except (ValueError, TypeError):
        return default


def _validate_date_param(value):
    if not value:
        return None
    try:
        datetime.strptime(value, DATE_FORMAT)
        return value
    except ValueError:
        return None


@require_http_methods(["GET"])
@login_required
@permission_required('audit.view_auditlog', raise_exception=True)
def get_audit_logs(request):
    """获取审计日志列表"""
    try:
        page = _validate_int_param(request.GET.get('page', 1), default=1, min_val=1, max_val=10000)
        page_size = _validate_int_param(request.GET.get('page_size', 20), default=20, min_val=1, max_val=MAX_PAGE_SIZE)
        action = request.GET.get('action', '')[:50] if request.GET.get('action') else None
        user_id = _validate_int_param(request.GET.get('user_id'), default=None, min_val=1) if request.GET.get('user_id') else None
        host_id = _validate_int_param(request.GET.get('host_id'), default=None, min_val=1) if request.GET.get('host_id') else None
        start_date = _validate_date_param(request.GET.get('start_date'))
        end_date = _validate_date_param(request.GET.get('end_date'))
        success = request.GET.get('success')
        search = request.GET.get('search', '')[:MAX_SEARCH_LENGTH]
        
        # 构建查询集
        queryset = AuditLog.objects.select_related('user', 'host').all()
        
        # 应用过滤器
        if action:
            queryset = queryset.filter(action=action)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if host_id:
            queryset = queryset.filter(host_id=host_id)
        if success is not None:
            queryset = queryset.filter(success=(success.lower() == 'true'))
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        if search:
            # 搜索用户、主机或操作详情
            from django.db.models import Q
            queryset = queryset.filter(
                Q(user__username__icontains=search) |
                Q(host__hostname__icontains=search) |
                Q(details__icontains=search) |
                Q(result__icontains=search)
            )
        
        # 按时间倒序排列
        queryset = queryset.order_by('-timestamp')
        
        # 分页
        paginator = Paginator(queryset, page_size)
        logs_page = paginator.get_page(page)
        
        # 构造响应数据
        result = {
            'success': True,
            'data': {
                'logs': [
                    {
                        'id': log.id,
                        'user': log.user.username if log.user else 'Anonymous',
                        'user_id': log.user.id if log.user else None,
                        'host': log.host.hostname if log.host else None,
                        'host_id': log.host.id if log.host else None,
                        'action': log.action,
                        'ip_address': log.ip_address,
                        'timestamp': log.timestamp.isoformat(),
                        'success': log.success,
                        'details': log.details,
                        'result': log.result
                    }
                    for log in logs_page
                ],
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': paginator.count,
                    'total_pages': paginator.num_pages,
                    'has_next': logs_page.has_next(),
                    'has_previous': logs_page.has_previous()
                }
            }
        }
        
        return JsonResponse(result)
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameter value'
        }, status=400)
    except Exception as e:
        logger.error(f"Error getting audit logs: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve audit logs'
        }, status=500)


@require_http_methods(["GET"])
@login_required
@permission_required('audit.view_sensitiveoperation', raise_exception=True)
def get_sensitive_operations(request):
    """获取敏感操作记录"""
    try:
        page = _validate_int_param(request.GET.get('page', 1), default=1, min_val=1, max_val=10000)
        page_size = _validate_int_param(request.GET.get('page_size', 20), default=20, min_val=1, max_val=MAX_PAGE_SIZE)
        user_id = _validate_int_param(request.GET.get('user_id'), default=None, min_val=1) if request.GET.get('user_id') else None
        operation_type = request.GET.get('operation_type', '')[:50] if request.GET.get('operation_type') else None
        start_date = _validate_date_param(request.GET.get('start_date'))
        end_date = _validate_date_param(request.GET.get('end_date'))
        
        queryset = SensitiveOperation.objects.select_related('user', 'approved_by').all()
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if operation_type:
            queryset = queryset.filter(operation_type=operation_type)
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        queryset = queryset.order_by('-timestamp')
        
        # 分页
        paginator = Paginator(queryset, page_size)
        ops_page = paginator.get_page(page)
        
        result = {
            'success': True,
            'data': {
                'operations': [
                    {
                        'id': op.id,
                        'operation_type': op.operation_type,
                        'user': op.user.username,
                        'user_id': op.user.id,
                        'target': op.target,
                        'timestamp': op.timestamp.isoformat(),
                        'ip_address': op.ip_address,
                        'justification': op.justification,
                        'approved_by': op.approved_by.username if op.approved_by else None,
                        'approved_at': op.approved_at.isoformat() if op.approved_at else None,
                        'result': op.result
                    }
                    for op in ops_page
                ],
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': paginator.count,
                    'total_pages': paginator.num_pages,
                    'has_next': ops_page.has_next(),
                    'has_previous': ops_page.has_previous()
                }
            }
        }
        
        return JsonResponse(result)
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameter value'
        }, status=400)
    except Exception as e:
        logger.error(f"Error getting sensitive operations: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve sensitive operations'
        }, status=500)


@require_http_methods(["GET"])
@login_required
@permission_required('audit.view_securityevent', raise_exception=True)
def get_security_events(request):
    """获取安全事件记录"""
    try:
        page = _validate_int_param(request.GET.get('page', 1), default=1, min_val=1, max_val=10000)
        page_size = _validate_int_param(request.GET.get('page_size', 20), default=20, min_val=1, max_val=MAX_PAGE_SIZE)
        event_type = request.GET.get('event_type', '')[:50] if request.GET.get('event_type') else None
        severity = request.GET.get('severity', '')[:20] if request.GET.get('severity') else None
        resolved = request.GET.get('resolved')
        user_id = _validate_int_param(request.GET.get('user_id'), default=None, min_val=1) if request.GET.get('user_id') else None
        start_date = _validate_date_param(request.GET.get('start_date'))
        end_date = _validate_date_param(request.GET.get('end_date'))
        
        queryset = SecurityEvent.objects.select_related('user', 'resolved_by').all()
        
        # 应用过滤器
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if severity:
            queryset = queryset.filter(severity=severity)
        if resolved is not None:
            queryset = queryset.filter(resolved=(resolved.lower() == 'true'))
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        queryset = queryset.order_by('-timestamp')
        
        # 分页
        paginator = Paginator(queryset, page_size)
        events_page = paginator.get_page(page)
        
        result = {
            'success': True,
            'data': {
                'events': [
                    {
                        'id': event.id,
                        'event_type': event.event_type,
                        'severity': event.severity,
                        'user': event.user.username if event.user else None,
                        'user_id': event.user.id if event.user else None,
                        'ip_address': event.ip_address,
                        'description': event.description,
                        'timestamp': event.timestamp.isoformat(),
                        'resolved': event.resolved,
                        'resolved_by': event.resolved_by.username if event.resolved_by else None,
                        'resolved_at': event.resolved_at.isoformat() if event.resolved_at else None,
                        'resolution_notes': event.resolution_notes
                    }
                    for event in events_page
                ],
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': paginator.count,
                    'total_pages': paginator.num_pages,
                    'has_next': events_page.has_next(),
                    'has_previous': events_page.has_previous()
                }
            }
        }
        
        return JsonResponse(result)
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameter value'
        }, status=400)
    except Exception as e:
        logger.error(f"Error getting security events: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve security events'
        }, status=500)


@login_required
@permission_required('audit.change_securityevent', raise_exception=True)
@require_http_methods(["POST"])
def mark_security_event_resolved(request):
    """标记安全事件为已解决"""
    try:
        data = json.loads(request.body.decode('utf-8'))
        event_id = data.get('event_id')
        resolution_notes = data.get('resolution_notes', '')
        
        if not event_id:
            return JsonResponse({
                'success': False,
                'error': 'Event ID is required'
            }, status=400)
        
        event = get_object_or_404(SecurityEvent, id=event_id)
        
        event.resolved = True
        event.resolved_by = request.user if request.user.is_authenticated else None
        event.resolved_at = timezone.now()
        event.resolution_notes = resolution_notes[:1000] if resolution_notes else ''
        event.save(update_fields=['resolved', 'resolved_by', 'resolved_at', 'resolution_notes'])
        
        return JsonResponse({
            'success': True,
            'message': 'Security event marked as resolved'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        logger.error(f"Error marking security event as resolved: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to resolve security event'
        }, status=500)


@require_http_methods(["GET"])
@login_required
@permission_required('audit.view_sessionactivity', raise_exception=True)
def get_user_session_activity(request):
    """获取用户会话活动记录"""
    try:
        user_id = _validate_int_param(request.GET.get('user_id'), default=None, min_val=1) if request.GET.get('user_id') else None
        page = _validate_int_param(request.GET.get('page', 1), default=1, min_val=1, max_val=10000)
        page_size = _validate_int_param(request.GET.get('page_size', 20), default=20, min_val=1, max_val=MAX_PAGE_SIZE)
        
        queryset = SessionActivity.objects.select_related('user').all()
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        queryset = queryset.order_by('-login_time')
        
        # 分页
        paginator = Paginator(queryset, page_size)
        sessions_page = paginator.get_page(page)
        
        result = {
            'success': True,
            'data': {
                'sessions': [
                    {
                        'id': session.id,
                        'user': session.user.username,
                        'user_id': session.user.id,
                        'session_key': session.session_key[:8] + '...',
                        'ip_address': session.ip_address,
                        'user_agent': session.user_agent[:100],  # 限制长度
                        'login_time': session.login_time.isoformat(),
                        'logout_time': session.logout_time.isoformat() if session.logout_time else None,
                        'is_active': session.is_active
                    }
                    for session in sessions_page
                ],
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': paginator.count,
                    'total_pages': paginator.num_pages,
                    'has_next': sessions_page.has_next(),
                    'has_previous': sessions_page.has_previous()
                }
            }
        }
        
        return JsonResponse(result)
        
    except ValueError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid parameter value'
        }, status=400)
    except Exception as e:
        logger.error(f"Error getting user session activity: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to retrieve session activity'
        }, status=500)


class AuditManagementView(View):
    """审计管理视图 - 需要审计权限"""
    
    @method_decorator(permission_required('audit.view_auditlog'))
    def get(self, request):
        """获取审计统计信息"""
        try:
            # 获取最近24小时的数据
            last_24h = timezone.now() - timedelta(hours=24)
            
            # 统计数据
            stats = {
                'total_logs': AuditLog.objects.count(),
                'recent_logs': AuditLog.objects.filter(timestamp__gte=last_24h).count(),
                'total_sensitive_ops': SensitiveOperation.objects.count(),
                'recent_sensitive_ops': SensitiveOperation.objects.filter(timestamp__gte=last_24h).count(),
                'total_security_events': SecurityEvent.objects.count(),
                'unresolved_security_events': SecurityEvent.objects.filter(resolved=False).count(),
                'recent_security_events': SecurityEvent.objects.filter(timestamp__gte=last_24h).count(),
            }
            
            # 按操作类型统计
            from django.db.models import Count
            action_stats = AuditLog.objects.values('action').annotate(count=Count('id')).order_by('-count')[:10]
            stats['top_actions'] = list(action_stats)
            
            # 按用户统计
            user_stats = AuditLog.objects.values('user__username').annotate(count=Count('id')).exclude(user__isnull=True).order_by('-count')[:10]
            stats['top_users'] = list(user_stats)
            
            # 按主机统计
            host_stats = AuditLog.objects.values('host__hostname').annotate(count=Count('id')).exclude(host__isnull=True).order_by('-count')[:10]
            stats['top_hosts'] = list(host_stats)
            
            return JsonResponse({
                'success': True,
                'data': stats
            })
            
        except Exception as e:
            logger.error(f"Error getting audit statistics: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to retrieve audit statistics'
            }, status=500)
    
    @method_decorator(permission_required('audit.delete_auditlog'))
    def delete(self, request):
        """清理审计日志"""
        try:
            data = json.loads(request.body.decode('utf-8'))
            days_to_keep = data.get('days_to_keep', 90)  # 默认保留90天
            
            cutoff_date = timezone.now() - timedelta(days=days_to_keep)
            
            # 删除旧的审计日志
            deleted_count, _ = AuditLog.objects.filter(timestamp__lt=cutoff_date).delete()
            
            # 删除旧的敏感操作记录
            deleted_sensitive, _ = SensitiveOperation.objects.filter(timestamp__lt=cutoff_date).delete()
            
            # 删除旧的安全事件记录（已解决的）
            deleted_events, _ = SecurityEvent.objects.filter(
                timestamp__lt=cutoff_date,
                resolved=True
            ).delete()
            
            return JsonResponse({
                'success': True,
                'data': {
                    'deleted_logs': deleted_count,
                    'deleted_sensitive_ops': deleted_sensitive,
                    'deleted_security_events': deleted_events,
                    'days_kept': days_to_keep
                }
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON in request body'
            }, status=400)
        except Exception as e:
            logger.error(f"Error cleaning audit logs: {str(e)}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'Failed to clean audit logs'
            }, status=500)


@require_http_methods(["GET"])
@login_required
@permission_required('audit.view_auditlog', raise_exception=True)
def export_audit_logs(request):
    """导出审计日志（CSV格式）"""
    try:
        # 获取查询参数
        action = request.GET.get('action', '')[:50] if request.GET.get('action') else None
        user_id = _validate_int_param(request.GET.get('user_id'), default=None, min_val=1) if request.GET.get('user_id') else None
        host_id = _validate_int_param(request.GET.get('host_id'), default=None, min_val=1) if request.GET.get('host_id') else None
        start_date = _validate_date_param(request.GET.get('start_date'))
        end_date = _validate_date_param(request.GET.get('end_date'))
        
        # 构建查询集
        queryset = AuditLog.objects.select_related('user', 'host').all()
        
        # 应用过滤器
        if action:
            queryset = queryset.filter(action=action)
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        if host_id:
            queryset = queryset.filter(host_id=host_id)
        if start_date:
            queryset = queryset.filter(timestamp__gte=start_date)
        if end_date:
            queryset = queryset.filter(timestamp__lte=end_date)
        
        # 按时间倒序排列
        queryset = queryset.order_by('-timestamp')
        
        # 生成CSV内容
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入标题行
        writer.writerow([
            'ID', 'User', 'Host', 'Action', 'IP Address', 'Timestamp', 
            'Success', 'Details', 'Result'
        ])
        
        # 写入数据行
        for log in queryset:
            writer.writerow([
                log.id,
                log.user.username if log.user else 'Anonymous',
                log.host.hostname if log.host else '',
                log.action,
                log.ip_address,
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.success,
                json.dumps(log.details, ensure_ascii=False) if log.details else '',
                log.result or ''
            ])
        
        # 获取CSV内容
        csv_content = output.getvalue()
        output.close()
        
        # 返回CSV文件
        from django.http import HttpResponse
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename=audit_logs_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv'
        
        return response
        
    except Exception as e:
        logger.error(f"Error exporting audit logs: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to export audit logs'
        }, status=500)