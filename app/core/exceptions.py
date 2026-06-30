"""全局异常与错误处理。"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

log = get_logger(__name__)


class AppError(Exception):
    """业务错误基类。"""

    def __init__(self, message: str, code: str = "app_error", status: int = 400):
        self.message = message
        self.code = code
        self.status = status
        super().__init__(message)


class AuthError(AppError):
    def __init__(self, message: str = "认证失败", code: str = "auth_error", status: int = 401):
        super().__init__(message, code, status)


class ForbiddenError(AppError):
    def __init__(self, message: str = "无权访问"):
        super().__init__(message, "forbidden", 403)


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, "not_found", 404)


class TenantError(AppError):
    def __init__(self, message: str = "租户解析失败"):
        super().__init__(message, "tenant_error", 404)


class RateLimitError(AppError):
    def __init__(self, message: str = "请求过于频繁"):
        super().__init__(message, "rate_limited", 429)


def _toast_html(message: str, kind: str = "error") -> str:
    """生成 OOB toast 片段（供 HTMX 请求错误时返回）。

    kind ∈ error | warning | info | success，对应不同主题色。
    """
    color_map = {
        "error": "var(--vercel-status-destructive)",
        "warning": "var(--vercel-status-warning)",
        "info": "var(--vercel-status-info)",
        "success": "var(--vercel-status-success)",
    }
    color = color_map.get(kind, color_map["error"])
    return (
        f'<div id="toast" hx-swap-oob="true" '
        f'style="position:fixed;top:16px;right:16px;z-index:100;'
        f'min-width:280px;max-width:400px;padding:12px 16px;border-radius:8px;'
        f"background:#ffffff;border:1px solid {color};"
        f'box-shadow:0 4px 12px rgba(0,0,0,0.08);'
        f'display:flex;align-items:flex-start;gap:8px;'
        f'animation:toast-in 0.2s ease-out;">'
        f'<span style="color:{color};font-weight:600;font-size:14px;'
        f'flex-shrink:0;margin-top:1px;">●</span>'
        f'<span style="color:var(--vercel-text-foreground);font-size:14px;'
        f'line-height:1.5;flex:1;">{message}</span>'
        f'<button onclick="this.parentElement.remove()" '
        f'style="background:none;border:none;cursor:pointer;color:'
        f'var(--vercel-text-muted-foreground);font-size:18px;line-height:1;'
        f'padding:0;margin-top:-2px;">×</button>'
        f'</div>'
        f'<style>@keyframes toast-in{{from{{opacity:0;transform:translateX(20px)}}'
        f'to{{opacity:1;transform:translateX(0)}}}}</style>'
        f'<script>setTimeout(function(){{var t=document.getElementById'
        f'("toast");if(t)t.remove()}},5000);</script>'
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError):
        # HTMX 请求返回 OOB toast 片段，错误信息会显示在页面右上角
        if _.headers.get("hx-request"):
            kind = "warning" if exc.status == 400 else "error"
            return HTMLResponse(_toast_html(exc.message, kind), status_code=exc.status)
        accept = _.headers.get("accept", "")
        if "text/html" in accept:
            return HTMLResponse(
                f'<div class="alert alert-danger">{exc.message}</div>', status_code=exc.status
            )
        return JSONResponse(
            {"error": exc.code, "message": exc.message}, status_code=exc.status
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(_: Request, exc: StarletteHTTPException):
        # HTMX 请求返回 toast 片段，普通请求返回 JSON 或重定向到错误页
        if _.headers.get("hx-request"):
            kind = "warning" if exc.status_code < 500 else "error"
            return HTMLResponse(
                _toast_html(str(exc.detail), kind), status_code=exc.status_code
            )
        if exc.status_code in (401,):
            return RedirectResponse(url="/login", status_code=303)
        return JSONResponse(
            {"error": "http_error", "message": str(exc.detail)},
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Request, exc: Exception):
        log.exception("unhandled_exception", error=str(exc))
        if _.headers.get("hx-request"):
            return HTMLResponse(_toast_html("服务器内部错误", "error"), status_code=500)
        return JSONResponse(
            {"error": "internal", "message": "服务器内部错误"}, status_code=500
        )
