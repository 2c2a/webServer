"""
2c2a - FastAPI + Huey 云电脑管理平台

主入口文件，配置 FastAPI 应用、中间件、路由、生命周期
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.database import engine, Base
from app.services.redis_helper import close_redis

settings = get_settings()

logger = logging.getLogger("2c2a")


# ========== 生命周期 ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info("2c2a 启动中...")
    logger.info(f"Debug 模式: {settings.debug}")
    logger.info(f"DEMO 模式: {settings.demo_mode}")

    # 创建数据库表（开发环境，生产环境用 Alembic）
    if settings.debug:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表已创建（开发模式）")

    # 预加载 Huey 任务（确保 periodic task 注册）
    import app.tasks  # noqa: F401

    yield

    # 关闭
    logger.info("2c2a 关闭中...")
    await close_redis()
    await engine.dispose()
    logger.info("2c2a 已关闭")


# ========== 创建应用 ==========

app = FastAPI(
    title="2c2a",
    description="云电脑管理平台",
    version="2.0.0",
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
)


# ========== 中间件（顺序重要，最后添加的最先执行） ==========

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 安全头
from app.middleware.security import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)

# 限流
from app.middleware.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# 站点组
from app.middleware.site_group import SiteGroupMiddleware
app.add_middleware(SiteGroupMiddleware)

# 维护模式
from app.middleware.maintenance import MaintenanceMiddleware
app.add_middleware(MaintenanceMiddleware)


# ========== 静态文件 ==========

from pathlib import Path

static_dir = Path(settings.static_dir)
if static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

media_dir = Path(settings.media_dir)
media_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")


# ========== 模板 ==========

templates = Jinja2Templates(directory=settings.template_dir)


# ========== 注册路由 ==========

from app.routers import (
    accounts,
    hosts,
    operations,
    dashboard,
    certificates,
    bootstrap,
    audit,
    tasks,
    themes,
    tickets,
    tunnel,
    provider,
    pages,
)

app.include_router(accounts.router)
app.include_router(hosts.router)
app.include_router(operations.router)
app.include_router(dashboard.router)
app.include_router(certificates.router)
app.include_router(bootstrap.router)
app.include_router(audit.router)
app.include_router(tasks.router)
app.include_router(themes.router)
app.include_router(tickets.router)
app.include_router(tunnel.router)
app.include_router(provider.router)
app.include_router(pages.router)


# ========== 全局异常处理 ==========

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """请求参数验证错误"""
    # 如果是页面请求，返回错误页面
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return templates.TemplateResponse(
            "errors/400.html",
            {"request": request, "errors": exc.errors()},
            status_code=422,
        )
    return JSONResponse(
        status_code=422,
        content={"success": False, "message": "请求参数错误", "errors": exc.errors()},
    )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return templates.TemplateResponse(
            "errors/404.html",
            {"request": request},
            status_code=404,
        )
    return JSONResponse(
        status_code=404,
        content={"success": False, "message": "资源不存在"},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return templates.TemplateResponse(
            "errors/500.html",
            {"request": request},
            status_code=500,
        )
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "服务器内部错误"},
    )


# ========== 健康检查 ==========

@app.get("/api/health", tags=["系统"])
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "version": "2.0.0"}
