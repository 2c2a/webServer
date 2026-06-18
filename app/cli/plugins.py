"""插件管理命令。

用法：
    2c2a plugin list                # 列出所有插件
    2c2a plugin info <id>           # 查看插件详情
    2c2a plugin enable <id>         # 启用插件
    2c2a plugin disable <id>        # 禁用插件
    2c2a plugin reload              # 重新发现并加载所有插件
    2c2a plugin routes              # 查看插件挂载的路由
    2c2a plugin services            # 查看插件注册的服务
"""
from __future__ import annotations

import asyncio

import typer

from app.cli.utils import console, error, info, print_table, success, warn
from app.plugins import get_plugin_manager
from app.plugins.loader import PluginLoader

plugin_app = typer.Typer(help="插件管理", no_args_is_help=True)


async def _load_plugins():
    """发现并加载所有插件（CLI 上下文）。"""
    manager = get_plugin_manager()
    loader = PluginLoader(manager)
    await loader.load_discovered()
    return manager


@plugin_app.command("list")
def list_plugins():
    """列出所有已发现的插件。"""
    manager = asyncio.run(_load_plugins())
    plugins = manager.list_plugins()
    if not plugins:
        info("未发现任何插件")
        return

    rows = [
        [
            p.get("plugin_id", p.get("id", "-")),
            p.get("name", "-"),
            p.get("version", "-"),
            "✓" if p.get("enabled", False) else "✗",
            p.get("description", "")[:40],
        ]
        for p in plugins
    ]
    print_table(
        f"插件列表（共 {len(plugins)} 个）",
        ["ID", "名称", "版本", "启用", "描述"],
        rows,
    )


@plugin_app.command("info")
def plugin_info(plugin_id: str = typer.Argument(..., help="插件 ID")):
    """查看插件详情。"""
    manager = asyncio.run(_load_plugins())
    plugin = manager.get_plugin(plugin_id)
    if plugin is None:
        error(f"插件 {plugin_id} 不存在")
        raise typer.Exit(1)

    console.print(f"\n[bold]插件详情[/bold]")
    console.print(f"  ID:        {plugin.plugin_id}")
    console.print(f"  名称:      {plugin.name}")
    console.print(f"  版本:      {plugin.version}")
    console.print(f"  描述:      {plugin.description or '-'}")
    console.print(f"  启用:      {'✓' if plugin.enabled else '✗'}")
    console.print(f"  类:        {type(plugin).__module__}.{type(plugin).__name__}")

    # 能力检测
    from app.plugins.base import RouteProvider, ServiceProvider, UIExtensionProvider

    capabilities = []
    if isinstance(plugin, RouteProvider):
        capabilities.append("路由提供者")
    if isinstance(plugin, ServiceProvider):
        capabilities.append(f"服务提供者({plugin.get_service_name()})")
    if isinstance(plugin, UIExtensionProvider):
        capabilities.append("UI 扩展提供者")
    console.print(f"  能力:      {', '.join(capabilities) or '-'}")

    # 路由
    if isinstance(plugin, RouteProvider):
        console.print("\n  [bold]路由:[/bold]")
        for prefix, router in manager.get_routers():
            if prefix.strip("/") == plugin_id:
                for route in router.routes:
                    path = getattr(route, "path", "?")
                    methods = getattr(route, "methods", set()) or set()
                    console.print(f"    {','.join(sorted(methods)):20s} {prefix}{path}")


@plugin_app.command("enable")
def enable_plugin(plugin_id: str = typer.Argument(..., help="插件 ID")):
    """启用插件。"""
    manager = asyncio.run(_load_plugins())

    async def _do():
        ok = await manager.enable_plugin(plugin_id)
        return ok

    ok = asyncio.run(_do())
    if ok:
        success(f"插件 {plugin_id} 已启用")
    else:
        error(f"启用失败：插件 {plugin_id} 不存在")
        raise typer.Exit(1)


@plugin_app.command("disable")
def disable_plugin(plugin_id: str = typer.Argument(..., help="插件 ID")):
    """禁用插件。"""
    manager = asyncio.run(_load_plugins())

    async def _do():
        ok = await manager.disable_plugin(plugin_id)
        return ok

    ok = asyncio.run(_do())
    if ok:
        warn(f"插件 {plugin_id} 已禁用")
    else:
        error(f"禁用失败：插件 {plugin_id} 不存在")
        raise typer.Exit(1)


@plugin_app.command("reload")
def reload_plugins():
    """重新发现并加载所有插件。"""
    manager = get_plugin_manager()

    async def _do():
        # 先卸载所有
        await manager.shutdown_all()
        manager.plugins.clear()
        # 重新发现加载
        loader = PluginLoader(manager)
        loaded = await loader.load_discovered()
        return loaded

    loaded = asyncio.run(_do())
    success(f"已重新加载 {len(loaded)} 个插件: {', '.join(loaded) or '无'}")


@plugin_app.command("routes")
def list_routes():
    """查看所有插件挂载的路由。"""
    manager = asyncio.run(_load_plugins())
    routers = manager.get_routers()
    if not routers:
        info("无插件路由")
        return

    rows = []
    for prefix, router in routers:
        for route in router.routes:
            path = getattr(route, "path", "?")
            methods = getattr(route, "methods", set()) or set()
            rows.append([prefix, ",".join(sorted(methods)), f"{prefix}{path}"])
    print_table("插件路由", ["挂载前缀", "方法", "完整路径"], rows)


@plugin_app.command("services")
def list_services():
    """查看插件注册的服务。"""
    manager = asyncio.run(_load_plugins())
    services = manager.service_registry.list_services()
    if not services:
        info("无已注册服务")
        return

    rows = [[name] for name in services]
    print_table("插件服务", ["服务名"], rows)


@plugin_app.command("scaffold")
def scaffold_plugin(
    plugin_id: str = typer.Argument(..., help="插件 ID（目录名）"),
    name: str = typer.Option(None, "--name", "-n", help="插件显示名"),
    description: str = typer.Option("", "--desc", "-d", help="插件描述"),
):
    """生成插件骨架。"""
    from pathlib import Path

    plugin_dir = Path(__file__).resolve().parent.parent / "plugins" / plugin_id
    if plugin_dir.exists():
        error(f"插件目录已存在: {plugin_dir}")
        raise typer.Exit(1)

    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(f'"""插件 {plugin_id} 包。"""\n')

    display_name = name or plugin_id
    plugin_code = f'''"""插件 {display_name}。"""
from __future__ import annotations

from fastapi import APIRouter

from app.plugins import PluginInterface, RouteProvider

__plugin_meta__ = {{
    "id": "{plugin_id}",
    "name": "{display_name}",
    "version": "0.1.0",
    "description": "{description}",
    "enabled": True,
}}


class Plugin(PluginInterface, RouteProvider):
    """{display_name} 插件实现。"""

    def __init__(self) -> None:
        super().__init__(
            plugin_id="{plugin_id}",
            name="{display_name}",
            version="0.1.0",
            description="{description}",
        )

    async def initialize(self) -> bool:
        return True

    async def shutdown(self) -> bool:
        return True

    def get_routers(self) -> list[APIRouter]:
        router = APIRouter()

        @router.get("/hello")
        async def hello():
            return {{"message": "Hello from {display_name}!"}}

        return [router]
'''
    (plugin_dir / "plugin.py").write_text(plugin_code)
    success(f"插件骨架已生成: {plugin_dir}")
    info(f"编辑 {plugin_dir}/plugin.py 实现功能，重启服务后自动加载")
