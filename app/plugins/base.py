"""插件基类与扩展接口。

参考原 Django 版插件系统（``plugins/core/base.py``），适配 FastAPI 异步架构：

* 所有生命周期方法（``initialize`` / ``shutdown`` / ``on_load`` / ``on_unload``）均为 ``async``；
* 路由通过 :class:`RouteProvider` 提供 ``fastapi.APIRouter``，由主应用在启动时挂载；
* UI 扩展面向 JinjaX 组件（``component`` 字段为 JinjaX 组件名）；
* 事件驱动通过 :class:`EventHook` 的 ``async emit`` 并发执行所有 handler。

本模块不依赖 Django。
"""
from __future__ import annotations

import abc
import asyncio
import enum
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

import fastapi

logger = logging.getLogger(__name__)


class LifecycleEvent(enum.Enum):
    """插件生命周期事件常量。

    用于 :class:`PluginManager` 的事件钩子命名，便于在插件加载 / 卸载 /
    启用 / 禁用时统一触发对应事件。
    """

    LOAD = "load"
    UNLOAD = "unload"
    ENABLE = "enable"
    DISABLE = "disable"


class PluginInterface(abc.ABC):
    """插件接口基类。

    所有原生插件必须继承此类，并实现 :meth:`initialize` 与 :meth:`shutdown`
    两个异步方法。``on_load`` / ``on_unload`` 为可选钩子，提供默认空实现。

    Parameters
    ----------
    plugin_id:
        插件唯一标识（建议使用小写 + 下划线，如 ``example``）。
    name:
        插件展示名称。
    version:
        语义化版本号，如 ``0.1.0``。
    description:
        插件描述，可为空。
    """

    def __init__(
        self,
        plugin_id: str,
        name: str,
        version: str,
        description: str = "",
    ) -> None:
        self.plugin_id = plugin_id
        self.name = name
        self.version = version
        self.description = description
        # 默认启用，可由 PluginManager.disable_plugin 置为 False
        self.enabled: bool = True

    @property
    def metadata(self) -> dict[str, Any]:
        """返回插件元数据字典。"""
        return {
            "id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "enabled": self.enabled,
        }

    @abc.abstractmethod
    async def initialize(self) -> bool:
        """插件初始化（异步）。

        在插件被加载时调用，用于建立数据库连接、预热缓存等。
        返回 ``True`` 表示初始化成功，``False`` 表示失败（将触发回滚）。
        """
        ...

    @abc.abstractmethod
    async def shutdown(self) -> bool:
        """插件关闭（异步）。

        在插件被卸载或应用关闭时调用，用于释放资源。
        返回 ``True`` 表示关闭成功。
        """
        ...

    async def on_load(self) -> None:
        """插件加载后钩子（可选，默认空）。

        在 :meth:`initialize` 成功后调用，可在此注册事件 handler 等。
        """
        return None

    async def on_unload(self) -> None:
        """插件卸载前钩子（可选，默认空）。

        在 :meth:`shutdown` 之前调用，可在此清理事件 handler 等。
        """
        return None


class ServiceProvider(abc.ABC):
    """服务提供者接口。

    插件可实现此接口以向 :class:`~app.plugins.registry.ServiceRegistry`
    注册可被其他插件发现的服务实例。
    """

    @abc.abstractmethod
    def get_service_name(self) -> str:
        """返回服务唯一名称。"""
        ...

    @abc.abstractmethod
    def get_service_interface(self) -> type:
        """返回服务实现的接口 / 协议类型，用于按类型建立索引。"""
        ...

    def get_service(self) -> Any:
        """返回服务实例，默认返回自身。"""
        return self


class RouteProvider(abc.ABC):
    """路由提供者接口。

    插件实现此接口以向主应用提供 ``fastapi.APIRouter``，主应用在启动时
    挂载这些路由。两种提供方式：

    1. :meth:`get_mount_paths`：显式声明 ``(前缀, router)`` 列表，优先使用；
    2. :meth:`get_routers`：仅返回 router 列表，由管理器按默认前缀
       ``/{plugin_id}`` 挂载。
    """

    @abc.abstractmethod
    def get_routers(self) -> list[fastapi.APIRouter]:
        """返回插件提供的 APIRouter 列表，供主应用挂载。"""
        ...

    def get_mount_paths(self) -> list[tuple[str, fastapi.APIRouter]]:
        """返回 ``(前缀, router)`` 列表，供主应用按指定前缀挂载。

        默认返回空列表，表示使用管理器的默认挂载策略。
        """
        return []


class UIExtensionProvider(abc.ABC):
    """UI 扩展提供者接口。

    插件实现此接口以向前端注入 JinjaX 组件扩展。扩展点（``slot``）由
    核心系统在各页面中预定义，插件只需声明要注入到哪个 slot。
    """

    @abc.abstractmethod
    def get_ui_extensions(self) -> list[UIExtension]:
        """返回 UI 扩展列表。"""
        ...


@dataclass
class UIExtension:
    """UI 扩展点描述对象。

    Attributes
    ----------
    extension_type:
        扩展类型，如 ``nav_item`` / ``section`` / ``form_field`` 等。
    slot:
        扩展槽位标识，由核心系统在页面中预定义。
    component:
        JinjaX 组件名，前端据此渲染对应组件。
    order:
        排序权重，越小越靠前，默认 ``0``。
    props:
        传递给组件的额外属性，可为 ``None``。
    """

    extension_type: str
    slot: str
    component: str
    order: int = 0
    props: dict[str, Any] | None = field(default=None)


# 异步 handler 类型：接受任意参数，返回协程
AsyncHandler = Callable[..., Coroutine[Any, Any, Any]]


class EventHook:
    """事件钩子。

    支持注册多个异步 handler，``emit`` 时通过 :func:`asyncio.gather` 并发
    执行所有 handler。单个 handler 抛出异常不会影响其他 handler 的执行，
    异常会被捕获并记录，对应结果位置为 ``None``。

    虽然 handler 约定为异步函数，但实现上兼容同步可调用对象（返回非
    awaitable 时直接采用其返回值），以提升健壮性。
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._handlers: list[AsyncHandler] = []

    def register(self, handler: AsyncHandler) -> None:
        """注册一个异步 handler（去重）。"""
        if handler not in self._handlers:
            self._handlers.append(handler)

    def unregister(self, handler: AsyncHandler) -> None:
        """取消注册 handler。"""
        if handler in self._handlers:
            self._handlers.remove(handler)

    @property
    def handlers(self) -> list[AsyncHandler]:
        """返回已注册 handler 的副本。"""
        return list(self._handlers)

    async def emit(self, *args: Any, **kwargs: Any) -> list[Any]:
        """并发触发所有 handler，返回与 handler 顺序对应的结果列表。"""
        if not self._handlers:
            return []
        # 每个 handler 包一层安全调用，避免单个异常中断整体
        tasks = [self._safe_call(handler, *args, **kwargs) for handler in list(self._handlers)]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _safe_call(self, handler: AsyncHandler, *args: Any, **kwargs: Any) -> Any:
        """安全调用单个 handler：捕获异常并兼容同步 / 异步 handler。"""
        try:
            result = handler(*args, **kwargs)
            # 若返回的是 awaitable（协程），则继续 await
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception:  # noqa: BLE001 - 钩子需隔离异常
            logger.exception(
                "事件钩子 %s 的 handler %s 执行失败",
                self.name,
                getattr(handler, "__name__", repr(handler)),
            )
            return None
