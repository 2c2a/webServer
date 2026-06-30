"""原生插件系统框架（FastAPI 异步）。

提供插件的全异步生命周期管理、路由挂载、UI 扩展、服务发现与事件驱动能力，
不依赖 Django。

典型用法::

    from app.plugins import get_plugin_manager, PluginLoader

    manager = get_plugin_manager()
    loader = PluginLoader(manager)
    await loader.load_discovered()          # 发现并加载所有插件

    # 应用启动时挂载插件路由
    for prefix, router in manager.get_routers():
        app.include_router(router, prefix=prefix)

公共导出
--------
"""
from __future__ import annotations

from app.plugins.base import (
    EventHook,
    LifecycleEvent,
    PluginInterface,
    RouteProvider,
    ServiceProvider,
    UIExtension,
    UIExtensionProvider,
)
from app.plugins.loader import PluginLoader, PluginManifest
from app.plugins.manager import PluginManager, get_plugin_manager, plugin_manager
from app.plugins.registry import ServiceRegistry

__all__ = [
    # 基类与扩展接口
    "PluginInterface",
    "ServiceProvider",
    "RouteProvider",
    "UIExtensionProvider",
    "UIExtension",
    "EventHook",
    "LifecycleEvent",
    # 服务注册表
    "ServiceRegistry",
    # 插件管理器
    "PluginManager",
    "plugin_manager",
    "get_plugin_manager",
    # 插件加载器
    "PluginLoader",
    "PluginManifest",
]
