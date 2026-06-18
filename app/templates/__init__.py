"""模板引擎：Jinja2（布局/页面/片段）+ JinjaX（可复用组件）。

- 布局/页面/片段：Jinja2 Environment + FileSystemLoader，支持 {% extends %} / {% include %}
- 可复用组件：JinjaX Catalog，支持 <x.Component /> 组件化
- 两者配合实现 App Shell 边缘缓存 + HTMX 动态片段精准分离
"""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinjax import Catalog

_TEMPLATES_DIR = Path(__file__).resolve().parent

# Jinja2 环境：布局、页面、片段
jinja_env = Environment(
    loader=FileSystemLoader(
        [
            str(_TEMPLATES_DIR / "layouts"),
            str(_TEMPLATES_DIR / "pages"),
            str(_TEMPLATES_DIR / "fragments"),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


async def render_template(template_name: str, **context) -> str:
    """异步渲染 Jinja2 模板。"""
    tpl = jinja_env.get_template(template_name)
    return await tpl.render_async(**context)


# JinjaX 组件目录
catalog = Catalog()
catalog.add_folder(_TEMPLATES_DIR / "components")


def render_component(component: str, **props) -> str:
    """渲染 JinjaX 组件。"""
    return catalog.render(component, **props)
