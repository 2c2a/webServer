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


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError):
        accept = _.headers.get("accept", "")
        if "text/html" in accept and not _.headers.get("hx-request"):
            return HTMLResponse(
                f'<div class="alert alert-danger">{exc.message}</div>', status_code=exc.status
            )
        return JSONResponse(
            {"error": exc.code, "message": exc.message}, status_code=exc.status
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc_handler(_: Request, exc: StarletteHTTPException):
        # HTMX 请求返回片段，普通请求返回 JSON 或重定向到错误页
        if _.headers.get("hx-request"):
            return HTMLResponse(
                f'<div class="alert alert-warning" hx-swap-oob="true" id="toast">'
                f"{exc.detail}</div>",
                status_code=exc.status_code,
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
            return HTMLResponse(
                '<div class="alert alert-danger" hx-swap-oob="true" id="toast">'
                "服务器内部错误</div>",
                status_code=500,
            )
        return JSONResponse(
            {"error": "internal", "message": "服务器内部错误"}, status_code=500
        )
