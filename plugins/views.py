"""
插件系统视图
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from .models import PluginRecord
from . import plugin_manager


@login_required
def plugin_list(request):
    """
    插件列表视图
    """
    plugins = PluginRecord.objects.all().order_by('-created_at')
    context = {
        'plugins': plugins
    }
    return render(request, 'plugins/list.html', context)


@login_required
def plugin_detail(request, plugin_id):
    """
    插件详情视图
    """
    plugin_record = get_object_or_404(PluginRecord, plugin_id=plugin_id)
    plugin_instance = plugin_manager.get_plugin(plugin_id)
    
    context = {
        'plugin_record': plugin_record,
        'plugin_instance': plugin_instance
    }
    return render(request, 'plugins/detail.html', context)


@user_passes_test(lambda u: u.is_staff)
@login_required
@require_POST
def toggle_plugin(request, plugin_id):
    """
    切换插件启用/禁用状态
    """
    try:
        plugin_record = get_object_or_404(PluginRecord, plugin_id=plugin_id)
        
        # 切换状态
        new_status = not plugin_record.is_active
        if new_status:
            plugin_manager.enable_plugin(plugin_id)
            messages.success(request, f'插件 "{plugin_record.name}" 已启用')
        else:
            plugin_manager.disable_plugin(plugin_id)
            messages.warning(request, f'插件 "{plugin_record.name}" 已禁用')
        
        # 更新数据库记录
        plugin_record.is_active = new_status
        plugin_record.save()
        
        return JsonResponse({
            'success': True,
            'new_status': new_status,
            'message': f'插件状态已更新为 {"启用" if new_status else "禁用"}'
        })
    except Exception as e:
        logger = __import__('logging').getLogger(__name__)
        logger.error(f"Error toggling plugin: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': '操作失败，请稍后重试'
        }, status=400)


@user_passes_test(lambda u: u.is_staff)
@login_required
def sync_plugins(request):
    """
    同步插件状态视图
    """
    try:
        # 从插件管理器同步插件到数据库
        for plugin in plugin_manager.get_all_plugins():
            plugin_record, created = PluginRecord.objects.get_or_create(
                plugin_id=plugin.plugin_id,
                defaults={
                    'name': plugin.name,
                    'version': plugin.version,
                    'description': plugin.description,
                    'is_active': plugin.enabled
                }
            )
            
            if not created:
                # 更新现有记录
                plugin_record.name = plugin.name
                plugin_record.version = plugin.version
                plugin_record.description = plugin.description
                plugin_record.is_active = plugin.enabled
                plugin_record.save()
        
        messages.success(request, f'成功同步了 {len(plugin_manager.get_all_plugins())} 个插件')
        return redirect('plugins:plugin_list')
    except Exception as e:
        messages.error(request, f'同步插件时出错: {str(e)}')
        return redirect('plugins:plugin_list')