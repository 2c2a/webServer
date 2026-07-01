"""FastAPI 应用工厂与生命周期管理。

技术栈：Granian + FastAPI + SQLAlchemy 2.0 Async + HTMX OOB + RedisHuey + JinjaX + aiohttp

启动方式：
    granian --interface asgi app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.v1.account_openings import router as account_openings_router
from app.api.v1.audit import router as audit_router
from app.api.v1.cloud_computers import router as cloud_computers_router
from app.api.v1.hosts import router as hosts_router
from app.api.v1.points import router as points_router
from app.api.v1.product_groups import router as product_groups_router
from app.api.v1.products import router as products_router
from app.api.v1.tickets import router as tickets_router
from app.auth.routes import router as auth_router
from app.captcha.router import router as captcha_router
from app.core.config import settings
from app.core.db import dispose_engine
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis
from app.tenant.middleware import TenantMiddleware
from app.web.admin import router as admin_router
from app.web.admin_fragments import router as admin_fragments_router
from app.web.admin_list_fragments import router as admin_list_fragments_router
from app.web.admin_detail_fragments import router as admin_detail_fragments_router
from app.web.fragments import router as fragments_router
from app.web.shell import router as shell_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理。"""
    setup_logging()
    log.info("app_starting", env=settings.env, debug=settings.debug)

    # 注册内置积分检测器
    try:
        from app.points.builtin import register_builtins

        register_builtins()
        log.info("points_detectors_registered")
    except Exception as e:  # noqa: BLE001
        log.warning("points_detectors_register_failed", error=str(e))

    # 注册内置验证码类型
    try:
        from app.captcha.builtin import register_builtins as register_captcha_builtins

        register_captcha_builtins()
        log.info("captcha_providers_registered")
    except Exception as e:  # noqa: BLE001
        log.warning("captcha_providers_register_failed", error=str(e))

    # 加载插件
    try:
        from app.plugins import get_plugin_manager
        from app.plugins.loader import PluginLoader

        manager = get_plugin_manager()
        loader = PluginLoader(manager)
        loaded = await loader.load_discovered()
        log.info("plugins_loaded", count=len(loaded), plugins=loaded)

        # 挂载插件路由
        for prefix, router in manager.get_routers():
            app.include_router(router, prefix=prefix)
            log.info("plugin_router_mounted", prefix=prefix)
    except Exception as e:  # noqa: BLE001
        log.warning("plugin_load_failed", error=str(e))

    log.info("app_started")
    yield

    # 关闭清理
    log.info("app_stopping")
    try:
        from app.plugins import get_plugin_manager

        await get_plugin_manager().shutdown_all()
    except Exception as e:  # noqa: BLE001
        log.warning("plugin_shutdown_failed", error=str(e))
    await close_redis()
    await dispose_engine()
    log.info("app_stopped")


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    app = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        description="Zero Agent Security Control Architecture - 异步架构",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    # 中间件：租户域名解析（最先执行）
    app.add_middleware(TenantMiddleware)

    # 异常处理
    register_exception_handlers(app)

    # 静态文件
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # 路由挂载
    # 1. 认证路由
    app.include_router(auth_router)
    # 2. App Shell 页面骨架（可缓存）
    app.include_router(shell_router)
    app.include_router(admin_router)
    # 2b. 验证码路由（公开，用于登录/注册前阶段）
    app.include_router(captcha_router)
    # 3. HTMX 动态片段（不可缓存）
    app.include_router(fragments_router)
    app.include_router(admin_fragments_router)
    app.include_router(admin_list_fragments_router)
    app.include_router(admin_detail_fragments_router)
    # 4. API v1
    api_prefix = "/api/v1"
    app.include_router(hosts_router, prefix=api_prefix)
    app.include_router(cloud_computers_router, prefix=api_prefix)
    app.include_router(account_openings_router, prefix=api_prefix)
    app.include_router(product_groups_router, prefix=api_prefix)
    app.include_router(products_router, prefix=api_prefix)
    app.include_router(tickets_router, prefix=api_prefix)
    app.include_router(audit_router, prefix=api_prefix)
    app.include_router(points_router, prefix=api_prefix)

    # 健康检查
    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": "2.0.0"}

    return app


app = create_app()
