"""HTMX 动态片段：用户导航、统计等动态内容。

策略（来自架构要求）：
- 用户导航、统计等动态内容由 HTMX 在页面加载后发起独立请求
- 服务端基于 Ed25519 验签和租户依赖实时返回不可缓存的 HTML 片段
- 片段响应标记为 no-store（不可缓存），确保数据安全隔离
- 支持 HTMX OOB（Out of Band）swap，一次请求更新多个区域
- 支持 ETag 协商缓存（片段内容未变时返回 304，降低带宽）
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from starlette.responses import HTMLResponse

from app.cache.keys import compute_etag, no_cache_headers


def fragment_response(
    html: str,
    *,
    request: Request | None = None,
    etag_parts: list[str] | None = None,
    extra_oob: list[str] | None = None,
) -> HTMLResponse:
    """返回 HTMX 片段响应（不可缓存）。

    - 标记 no-store，确保动态内容不被 CDN/浏览器缓存
    - 可选 ETag 协商（etag_parts 变化时才返回新内容）
    - extra_oob：额外的 OOB 片段 HTML（拼接到主片段后，HTMX 自动 swap）
    """
    headers = no_cache_headers()

    # ETag 协商缓存
    if etag_parts and request is not None:
        etag = compute_etag(*etag_parts)
        headers["ETag"] = etag
        if request.headers.get("if-none-match") == etag:
            return HTMLResponse(status_code=304, headers=headers)

    content = html
    if extra_oob:
        content = html + "".join(extra_oob)

    return HTMLResponse(content=content, headers=headers)


def oob_fragment(target_id: str, html: str, *, swap: str = "outerHTML") -> str:
    """构造 HTMX OOB 片段。

    HTMX OOB 允许一次响应更新多个 DOM 区域：
    <div id="nav" hx-swap-oob="outerHTML">...</div>
    """
    return f'<div id="{target_id}" hx-swap-oob="{swap}">{html}</div>'


def htmx_trigger(event_name: str, payload: Any = None) -> dict[str, str]:
    """生成 HTMX 触发事件响应头。

    用于服务端主动触发前端事件（如任务完成通知）。
    """
    import json

    if payload is None:
        return {"HX-Trigger": event_name}
    return {"HX-Trigger": json.dumps({event_name: payload})}


def htmx_redirect(url: str) -> dict[str, str]:
    """生成 HTMX 重定向响应头。"""
    return {"HX-Redirect": url}


def htmx_refresh() -> dict[str, str]:
    """生成 HTMX 刷新响应头。"""
    return {"HX-Refresh": "true"}
