"""服务注册表：插件间服务发现。

:class:`ServiceRegistry` 管理插件（实现了
:class:`~app.plugins.base.ServiceProvider` 的插件）提供的服务实例，
支持按服务名称与接口类型两种方式查找。
"""
from __future__ import annotations

import logging
from typing import Any

from app.plugins.base import ServiceProvider

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """服务注册表。

    内部维护两张索引：

    * ``_services``：服务名 -> 服务实例；
    * ``_interfaces``：接口类型 -> 服务名列表（保持注册顺序）。
    """

    def __init__(self) -> None:
        # 服务名 -> 服务实例
        self._services: dict[str, Any] = {}
        # 接口类型 -> 服务名列表
        self._interfaces: dict[type, list[str]] = {}

    def register(self, provider: ServiceProvider) -> None:
        """注册服务提供者。

        按 ``service_name`` 存储实例，并按 ``interface`` 类型建立索引。
        若同名服务已存在则覆盖。
        """
        name = provider.get_service_name()
        interface = provider.get_service_interface()
        service = provider.get_service()

        self._services[name] = service

        names = self._interfaces.setdefault(interface, [])
        if name not in names:
            names.append(name)

        logger.info(
            "服务已注册: %s (接口: %s)",
            name,
            getattr(interface, "__name__", interface),
        )

    def get(self, name: str) -> Any | None:
        """按服务名获取实例，不存在返回 ``None``。"""
        return self._services.get(name)

    def get_by_interface(self, interface: type) -> Any | None:
        """按接口类型获取第一个匹配的服务实例。

        若有多个实现，返回注册顺序中的第一个；无匹配返回 ``None``。
        """
        for name in self._interfaces.get(interface, []):
            if name in self._services:
                return self._services[name]
        return None

    def list_services(self) -> list[str]:
        """返回所有已注册的服务名列表。"""
        return list(self._services.keys())

    def unregister(self, name: str) -> None:
        """按服务名注销服务，同时清理接口索引。"""
        if name not in self._services:
            return
        del self._services[name]
        for names in self._interfaces.values():
            if name in names:
                names.remove(name)
        logger.info("服务已注销: %s", name)
