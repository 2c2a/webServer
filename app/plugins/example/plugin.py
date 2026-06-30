"""最小示例插件。

演示如何通过 :class:`~app.plugins.base.PluginInterface` +
:class:`~app.plugins.base.RouteProvider` 提供一个异步 JSON 路由
（``GET /example/hello``），验证插件机制可用。

被 :class:`~app.plugins.loader.PluginLoader` 自动发现：

* 模块级 ``__plugin_meta__`` 提供元数据；
* ``Plugin`` 类为入口（``PluginInterface`` 子类），无参实例化。
"""
from __future__ import annotations

import fastapi

from app.plugins.base import PluginInterface, RouteProvider

# 模块级插件元数据（PluginLoader 优先读取此处）
__plugin_meta__ = {
    "id": "example",
    "name": "示例插件",
    "version": "0.1.0",
    "description": "最小示例插件，验证插件机制可用",
    "enabled": True,
}


class Plugin(PluginInterface, RouteProvider):
    """示例插件：提供 ``GET /example/hello`` 路由。"""

    def __init__(self) -> None:
        super().__init__(
            plugin_id=__plugin_meta__["id"],
            name=__plugin_meta__["name"],
            version=__plugin_meta__["version"],
            description=__plugin_meta__["description"],
        )
        # 在 __init__ 中构建路由，确保 get_routers() 在任意时机可用
        self.router = fastapi.APIRouter()
        self.router.add_api_route(
            "/hello",
            self.hello,
            methods=["GET"],
            name="example_hello",
            summary="示例插件问候接口",
        )

    async def initialize(self) -> bool:
        # 示例插件无需额外资源初始化
        return True

    async def shutdown(self) -> bool:
        return True

    async def hello(self) -> dict[str, str]:
        """返回示例 JSON 响应。"""
        return {
            "message": "Hello from Example Plugin!",
            "plugin": self.plugin_id,
            "version": self.version,
        }

    # ── RouteProvider 实现 ──
    def get_routers(self) -> list[fastapi.APIRouter]:
        # 使用管理器默认挂载策略：前缀 /{plugin_id} -> /example
        # 配合路由 /hello，最终路径为 /example/hello
        return [self.router]
