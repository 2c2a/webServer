"""插件管理器（单例）。

:class:`PluginManager` 是插件系统的核心协调者，负责：

* 插件实例的注册 / 获取 / 列举；
* 异步生命周期管理（加载 / 卸载 / 启用 / 禁用），失败时回滚已注册的服务；
* 收集 :class:`~app.plugins.base.RouteProvider` 提供的路由供主应用挂载；
* 收集 :class:`~app.plugins.base.UIExtensionProvider` 提供的 UI 扩展；
* 通过 :class:`~app.plugins.registry.ServiceRegistry` 实现插件间服务发现；
* 通过 :class:`~app.plugins.base.EventHook` 实现事件驱动（async emit）。

模块级提供单例 :data:`plugin_manager` 与 :func:`get_plugin_manager`。
"""
from __future__ import annotations

import logging
from typing import Any

import fastapi

from app.plugins.base import (
    EventHook,
    LifecycleEvent,
    PluginInterface,
    RouteProvider,
    ServiceProvider,
    UIExtension,
    UIExtensionProvider,
)
from app.plugins.registry import ServiceRegistry

logger = logging.getLogger(__name__)


class PluginManager:
    """插件管理器。"""

    def __init__(self) -> None:
        # plugin_id -> 插件实例
        self.plugins: dict[str, PluginInterface] = {}
        # 服务注册表（插件间服务发现）
        self.service_registry: ServiceRegistry = ServiceRegistry()
        # 事件名 -> EventHook
        self.event_hooks: dict[str, EventHook] = {}
        # 预置生命周期事件钩子，便于插件在 on_load 中注册 handler
        for event in LifecycleEvent:
            self.register_event(event.value)

    # ───────────────────────── 注册 / 获取 ─────────────────────────

    def register_plugin(self, plugin: PluginInterface) -> None:
        """注册插件实例（仅登记，不触发加载）。"""
        if plugin.plugin_id in self.plugins:
            logger.warning("插件 %s 已注册，将覆盖旧实例", plugin.plugin_id)
        self.plugins[plugin.plugin_id] = plugin
        logger.info("插件已注册: %s (ID: %s)", plugin.name, plugin.plugin_id)

    def get_plugin(self, plugin_id: str) -> PluginInterface | None:
        """按 ID 获取插件实例。"""
        return self.plugins.get(plugin_id)

    def list_plugins(self) -> list[dict[str, Any]]:
        """返回所有插件的元数据列表。"""
        return [plugin.metadata for plugin in self.plugins.values()]

    # ───────────────────────── 生命周期 ─────────────────────────

    async def load_plugin(self, plugin_id: str) -> bool:
        """加载插件：调用 ``initialize()`` + ``on_load()``，失败回滚。

        若插件是 :class:`ServiceProvider`，会在初始化前注册其服务；
        一旦 ``initialize`` 失败或抛异常，将回滚已注册的服务。
        """
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            logger.warning("加载失败：插件 %s 不存在", plugin_id)
            return False
        if not plugin.enabled:
            logger.info("插件 %s 已禁用，跳过加载", plugin_id)
            return False

        # 服务提供者：先注册服务，便于 initialize 内部使用
        if isinstance(plugin, ServiceProvider):
            try:
                self.service_registry.register(plugin)
            except Exception:  # noqa: BLE001
                logger.exception("插件 %s 服务注册失败", plugin_id)

        try:
            ok = await plugin.initialize()
            if not ok:
                logger.warning("插件 %s initialize() 返回 False", plugin_id)
                self._rollback_service(plugin)
                return False
            await plugin.on_load()
            await self.emit_event(LifecycleEvent.LOAD.value, plugin=plugin)
            logger.info("插件已加载: %s", plugin.name)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("加载插件 %s 时发生错误", plugin_id)
            self._rollback_service(plugin)
            return False

    async def unload_plugin(self, plugin_id: str) -> bool:
        """卸载插件：调用 ``on_unload()`` + ``shutdown()``，并注销服务。"""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            logger.warning("卸载失败：插件 %s 不存在", plugin_id)
            return False

        try:
            await plugin.on_unload()
            await self.emit_event(LifecycleEvent.UNLOAD.value, plugin=plugin)
            ok = await plugin.shutdown()
            if not ok:
                logger.warning("插件 %s shutdown() 返回 False", plugin_id)
        except Exception:  # noqa: BLE001
            logger.exception("卸载插件 %s 时发生错误", plugin_id)
            ok = False
        finally:
            # 无论成功与否都尝试注销服务，避免残留
            self._rollback_service(plugin)

        logger.info("插件已卸载: %s", plugin.name)
        return bool(ok)

    async def enable_plugin(self, plugin_id: str) -> bool:
        """启用插件并触发 ``enable`` 事件。"""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            logger.warning("启用失败：插件 %s 不存在", plugin_id)
            return False
        plugin.enabled = True
        await self.emit_event(LifecycleEvent.ENABLE.value, plugin=plugin)
        logger.info("插件已启用: %s", plugin_id)
        return True

    async def disable_plugin(self, plugin_id: str) -> bool:
        """禁用插件并触发 ``disable`` 事件。"""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            logger.warning("禁用失败：插件 %s 不存在", plugin_id)
            return False
        plugin.enabled = False
        await self.emit_event(LifecycleEvent.DISABLE.value, plugin=plugin)
        logger.info("插件已禁用: %s", plugin_id)
        return True

    async def load_all(self) -> None:
        """加载所有已注册插件。"""
        for plugin_id in list(self.plugins.keys()):
            await self.load_plugin(plugin_id)

    async def shutdown_all(self) -> None:
        """关闭所有插件（按注册逆序卸载）。"""
        for plugin_id in reversed(list(self.plugins.keys())):
            await self.unload_plugin(plugin_id)

    def _rollback_service(self, plugin: PluginInterface) -> None:
        """回滚插件已注册的服务（若其为服务提供者）。"""
        if isinstance(plugin, ServiceProvider):
            try:
                self.service_registry.unregister(plugin.get_service_name())
            except Exception:  # noqa: BLE001
                logger.debug("回滚服务时出错（可忽略）", exc_info=True)

    # ───────────────────────── 路由 / UI 扩展收集 ─────────────────────────

    def get_routers(self) -> list[tuple[str, fastapi.APIRouter]]:
        """收集所有 ``RouteProvider`` 的路由，返回 ``(mount_path, router)`` 列表。

        优先使用 :meth:`RouteProvider.get_mount_paths` 的显式声明；
        否则使用默认前缀 ``/{plugin_id}`` 挂载 :meth:`RouteProvider.get_routers`
        返回的每个 router。已禁用的插件会被跳过。
        """
        routers: list[tuple[str, fastapi.APIRouter]] = []
        for plugin in self.plugins.values():
            if not isinstance(plugin, RouteProvider):
                continue
            if not plugin.enabled:
                continue
            try:
                mount_paths = plugin.get_mount_paths()
                if mount_paths:
                    routers.extend(mount_paths)
                    continue
                # 默认挂载策略：/{plugin_id} 下挂载每个 router
                prefix = f"/{plugin.plugin_id}"
                for router in plugin.get_routers():
                    routers.append((prefix, router))
            except Exception:  # noqa: BLE001
                logger.exception("收集插件 %s 路由失败", plugin.plugin_id)
        return routers

    def get_ui_extensions(self) -> list[UIExtension]:
        """收集所有 ``UIExtensionProvider`` 的扩展，按 ``order`` 升序排序。"""
        extensions: list[UIExtension] = []
        for plugin in self.plugins.values():
            if not isinstance(plugin, UIExtensionProvider):
                continue
            if not plugin.enabled:
                continue
            try:
                extensions.extend(plugin.get_ui_extensions())
            except Exception:  # noqa: BLE001
                logger.exception("收集插件 %s UI 扩展失败", plugin.plugin_id)
        extensions.sort(key=lambda ext: ext.order)
        return extensions

    # ───────────────────────── 服务 / 事件 ─────────────────────────

    def service(self, name: str) -> Any | None:
        """快捷访问 ``service_registry.get(name)``。"""
        return self.service_registry.get(name)

    def register_event(self, name: str) -> EventHook:
        """创建或获取事件钩子。"""
        hook = self.event_hooks.get(name)
        if hook is None:
            hook = EventHook(name)
            self.event_hooks[name] = hook
        return hook

    async def emit_event(self, name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """触发指定名称的事件，并发执行所有 handler。"""
        hook = self.event_hooks.get(name)
        if hook is None:
            return []
        return await hook.emit(*args, **kwargs)


# 模块级单例
plugin_manager = PluginManager()


def get_plugin_manager() -> PluginManager:
    """返回模块级单例 :class:`PluginManager`。"""
    return plugin_manager
