"""模板引擎：Jinja2（布局/页面/片段）+ JinjaX（可复用组件）。

- 布局/页面/片段：Jinja2 Environment + FileSystemLoader，支持 {% extends %} / {% include %}
- 可复用组件：JinjaX Catalog，支持 <x.Component /> 组件化
- 两者配合实现 App Shell 边缘缓存 + HTMX 动态片段精准分离
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinjax import Catalog

_TEMPLATES_DIR = Path(__file__).resolve().parent


def _finalize(value):
    """渲染前对值做最终处理。

    Jinja2 默认会把 None 渲染为字符串 "None"，在 HTML 中显示为 "None"。
    这里统一将 None 转为空字符串，避免空值字段显示 "None" 文本。
    """
    return "" if value is None else value


def _relative_time(value) -> str:
    """相对时间格式化：刚刚 / X分钟前 / X小时前 / 昨天 / X天前 / X周前 / YYYY-MM-DD。

    模板里使用 `{{ obj.created_at|relative_time }}`。
    """
    if not value:
        return ""
    dt = value
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if not isinstance(dt, datetime):
        return str(value)

    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60}分钟前"
    if seconds < 86400:
        return f"{seconds // 3600}小时前"
    if seconds < 172800:  # < 2 天
        return "昨天"
    if seconds < 604800:  # < 7 天
        return f"{seconds // 86400}天前"
    if seconds < 2419200:  # < 4 周
        return f"{seconds // 604800}周前"
    return dt.strftime("%Y-%m-%d")


# Jinja2 环境：布局、页面、片段、邮件
jinja_env = Environment(
    loader=FileSystemLoader(
        [
            str(_TEMPLATES_DIR / "layouts"),
            str(_TEMPLATES_DIR / "pages"),
            str(_TEMPLATES_DIR / "fragments"),
            str(_TEMPLATES_DIR / "emails"),
        ]
    ),
    autoescape=select_autoescape(["html", "xml"]),
    enable_async=True,
    trim_blocks=True,
    lstrip_blocks=True,
    finalize=_finalize,
)
# 注册相对时间过滤器
jinja_env.filters["relative_time"] = _relative_time


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
