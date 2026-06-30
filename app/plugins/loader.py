"""插件发现与加载。

基于目录扫描的插件发现机制：

* 每个插件目录需含 ``plugin.py`` 文件，其中定义 ``Plugin`` 类
  （:class:`~app.plugins.base.PluginInterface` 子类）；
* 默认扫描 ``app.plugins`` 包目录下的子目录（如 ``app/plugins/example/``），
  也可通过 ``plugin_dirs`` 自定义扫描路径；
* 插件元数据优先从模块级变量 ``__plugin_meta__`` 读取，否则从 ``Plugin``
  类属性读取，最后以目录名兜底。

``__plugin_meta__`` 示例::

    __plugin_meta__ = {
        "id": "example",
        "name": "示例插件",
        "version": "0.1.0",
        "description": "最小示例插件",
        "enabled": True,
    }
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.plugins.base import PluginInterface
from app.plugins.manager import PluginManager

logger = logging.getLogger(__name__)


@dataclass
class PluginManifest:
    """插件清单（发现阶段产出的描述信息）。

    Attributes
    ----------
    plugin_id:
        插件唯一标识。
    name:
        插件展示名称。
    version:
        版本号。
    description:
        描述。
    module_path:
        插件入口模块的导入路径（如 ``app.plugins.example.plugin``）。
    enabled:
        是否启用。
    """

    plugin_id: str
    name: str
    version: str
    description: str
    module_path: str
    enabled: bool = True


class PluginLoader:
    """插件加载器。

    扫描插件目录发现插件，并交由 :class:`PluginManager` 实例化与加载。
    """

    #: 插件入口文件名
    PLUGIN_ENTRY_FILE = "plugin.py"
    #: 插件入口类名
    PLUGIN_ENTRY_CLASS = "Plugin"

    def __init__(
        self,
        manager: PluginManager,
        plugin_dirs: list[Path] | None = None,
    ) -> None:
        self.manager = manager
        # 默认扫描 app.plugins 包目录（本文件所在目录）
        if plugin_dirs is None:
            plugin_dirs = [Path(__file__).resolve().parent]
        self.plugin_dirs = plugin_dirs

    # ───────────────────────── 发现 ─────────────────────────

    def discover(self) -> list[PluginManifest]:
        """扫描插件目录，返回 manifest 列表。

        每个插件目录需含 ``plugin.py`` 文件。重复的 ``plugin_id`` 会被跳过。
        """
        manifests: list[PluginManifest] = []
        seen_ids: set[str] = set()

        for base_dir in self.plugin_dirs:
            if not base_dir.is_dir():
                logger.debug("插件目录不存在或非目录: %s", base_dir)
                continue
            for entry in sorted(base_dir.iterdir(), key=lambda p: p.name):
                if not entry.is_dir():
                    continue
                # 跳过 __pycache__ / .开头 等非插件目录
                if entry.name.startswith("_") or entry.name.startswith("."):
                    continue
                plugin_file = entry / self.PLUGIN_ENTRY_FILE
                if not plugin_file.is_file():
                    continue
                manifest = self._build_manifest(entry, plugin_file)
                if manifest is None:
                    continue
                if manifest.plugin_id in seen_ids:
                    logger.warning("跳过重复插件 ID: %s (%s)", manifest.plugin_id, entry)
                    continue
                seen_ids.add(manifest.plugin_id)
                manifests.append(manifest)

        logger.info("共发现 %d 个插件", len(manifests))
        return manifests

    def _build_manifest(self, plugin_dir: Path, plugin_file: Path) -> PluginManifest | None:
        """根据插件目录构建 manifest。

        元数据优先级：模块级 ``__plugin_meta__`` > ``Plugin`` 类属性 > 目录名兜底。
        """
        module_name = self._module_name_for(plugin_dir)
        try:
            module = self._import_plugin_module(module_name, plugin_file)
        except Exception:  # noqa: BLE001
            logger.exception("导入插件模块失败: %s", plugin_file)
            return None

        # 优先读取模块级 __plugin_meta__
        meta: dict[str, Any] = {}
        module_meta = getattr(module, "__plugin_meta__", None)
        if isinstance(module_meta, dict):
            meta = module_meta

        plugin_cls = getattr(module, self.PLUGIN_ENTRY_CLASS, None)
        if plugin_cls is None or not (
            inspect.isclass(plugin_cls) and issubclass(plugin_cls, PluginInterface)
        ):
            logger.error(
                "插件 %s 中未找到有效的 %s 类（需为 PluginInterface 子类）",
                plugin_file,
                self.PLUGIN_ENTRY_CLASS,
            )
            return None

        # 从 __plugin_meta__ 读取，缺失则回退到 Plugin 类属性，最后目录名兜底
        plugin_id = (
            meta.get("id")
            or getattr(plugin_cls, "plugin_id", None)
            or plugin_dir.name
        )
        name = meta.get("name") or getattr(plugin_cls, "name", None) or plugin_id
        version = meta.get("version") or getattr(plugin_cls, "version", None) or "0.0.0"
        description = (
            meta.get("description")
            or getattr(plugin_cls, "description", None)
            or ""
        )
        enabled = bool(meta.get("enabled", True))

        return PluginManifest(
            plugin_id=plugin_id,
            name=name,
            version=version,
            description=description,
            module_path=module_name,
            enabled=enabled,
        )

    def _module_name_for(self, plugin_dir: Path) -> str:
        """根据插件目录推导模块导入路径。

        假设插件位于 ``app.plugins`` 包下，例如
        ``app/plugins/example/`` -> ``app.plugins.example.plugin``。
        若路径中找不到 ``app`` 段，则回退为以目录名作为顶层模块。
        """
        parts = plugin_dir.parts
        try:
            idx = parts.index("app")
            base_parts = parts[idx:]
        except ValueError:
            base_parts = (plugin_dir.name,)
        return ".".join([*base_parts, "plugin"])

    def _import_plugin_module(self, module_name: str, plugin_file: Path):
        """导入插件模块。

        优先使用标准 :func:`importlib.import_module`（依赖 ``app.plugins``
        包可被导入）；若失败则回退到从文件路径加载并注册到 ``sys.modules``。
        """
        try:
            return importlib.import_module(module_name)
        except ImportError:
            logger.debug("标准导入 %s 失败，回退到文件路径加载", module_name)
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法为 {plugin_file} 创建模块规格") from None
            module = importlib.util.module_from_spec(spec)
            # 注册到 sys.modules，便于 load_discovered 阶段复用
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            return module

    # ───────────────────────── 加载 ─────────────────────────

    async def load_discovered(self) -> list[str]:
        """发现并加载所有插件。

        流程：``discover`` -> 实例化 ``Plugin`` -> ``register_plugin`` ->
        ``load_plugin``。返回成功加载的 ``plugin_id`` 列表。
        """
        manifests = self.discover()
        loaded: list[str] = []

        for manifest in manifests:
            # discover 阶段已导入并缓存模块，此处直接复用
            try:
                module = importlib.import_module(manifest.module_path)
            except Exception:  # noqa: BLE001
                logger.exception("加载插件模块失败: %s", manifest.module_path)
                continue

            plugin_cls = getattr(module, self.PLUGIN_ENTRY_CLASS, None)
            if plugin_cls is None or not (
                inspect.isclass(plugin_cls) and issubclass(plugin_cls, PluginInterface)
            ):
                logger.error(
                    "插件 %s 缺少有效的 %s 类",
                    manifest.module_path,
                    self.PLUGIN_ENTRY_CLASS,
                )
                continue

            try:
                plugin = plugin_cls()
            except Exception:  # noqa: BLE001
                logger.exception("实例化插件 %s 失败", manifest.module_path)
                continue

            # 用 manifest 的 enabled 标记覆盖实例状态
            if not manifest.enabled:
                plugin.enabled = False

            self.manager.register_plugin(plugin)
            ok = await self.manager.load_plugin(plugin.plugin_id)
            if ok:
                loaded.append(plugin.plugin_id)

        logger.info("成功加载 %d 个插件: %s", len(loaded), loaded)
        return loaded
