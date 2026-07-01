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

    # 启动前安全断言：禁止 demo/debug 模式在生产环境误启用
    settings.assert_safe_to_run()

    # demo 模式醒目警告横幅
    if settings.demo:
        _print_demo_banner()

    log.info("app_starting", env=settings.env, debug=settings.debug, demo=settings.demo)

    # demo 模式：自动预置演示账号（若库中无超管）
    if settings.demo:
        try:
            await _auto_seed_demo_accounts()
        except Exception as e:  # noqa: BLE001
            log.warning("demo_auto_seed_failed", error=str(e))

    # demo 模式：每次启动清理并重建演示业务数据（保证演示环境干净）
    if settings.demo:
        try:
            await _auto_reset_demo_business_data()
        except Exception as e:  # noqa: BLE001
            log.warning("demo_business_data_reset_failed", error=str(e))

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


def _print_demo_banner() -> None:
    """输出醒目的 DEMO 模式警告横幅到日志。"""
    banner = (
        "\n"
        "╔══════════════════════════════════════════════════════════════╗\n"
        "║                    ⚠  DEMO 模式已启用  ⚠                    ║\n"
        "║                                                              ║\n"
        "║  · 密钥从 SECRET_KEY 派生（弱密钥，仅用于演示）             ║\n"
        "║  · WinRM 操作返回模拟结果（不实际执行任何远程命令）         ║\n"
        "║  · 演示账号已预置（见控制台输出）                           ║\n"
        "║  · 禁止用于生产环境，所有数据可被任意访问                   ║\n"
        "║                                                              ║\n"
        "║  关闭方式：在 .env 中设置 2C2A_DEMO=0                        ║\n"
        "╚══════════════════════════════════════════════════════════════╝"
    )
    # 用 warning 级别确保在日志中显眼
    log.warning(banner)


async def _auto_seed_demo_accounts() -> None:
    """demo 模式启动时自动预置演示账号（若库中无任何超管）。

    幂等：库中已有超管则跳过，避免覆盖用户修改。
    """
    from sqlalchemy import select

    from app.cli.account import DEMO_ACCOUNTS, DEMO_PASSWORD, seed_demo_accounts
    from app.core.db import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.is_superuser == True).limit(1)  # noqa: E712
        )
        has_superuser = result.scalar_one_or_none() is not None

    if has_superuser:
        log.info("demo_seed_skipped", reason="superuser_exists")
        return

    result = await seed_demo_accounts()
    created = result["created"]
    skipped = result["skipped"]
    log.warning(
        "demo_accounts_seeded",
        created=created,
        skipped=skipped,
        password=DEMO_PASSWORD,
    )
    # 控制台友好输出（便于演示时查看账号）
    print("\n" + "=" * 60)
    print("  DEMO 演示账号已预置（密码统一: demo123456）")
    print("=" * 60)
    for spec in DEMO_ACCOUNTS:
        status = "✓ 新建" if spec["username"] in created else "· 已存在"
        print(f"  {spec['username']:<16} | {spec['label']:<8} | {status}")
    print("=" * 60 + "\n")


async def _auto_reset_demo_business_data() -> None:
    """demo 模式启动时清理并重建演示业务数据。

    每次启动都重建，保证演示环境是干净的。
    """
    from app.cli.demo_data import reset_demo_business_data

    result = await reset_demo_business_data()
    cleaned = result["cleaned"]["deleted"]
    created = result["seeded"]["created"]

    log.info("demo_business_data_reset", cleaned=cleaned, created=created)

    # 控制台友好输出
    print("\n" + "-" * 60)
    print("  DEMO 业务数据已重建")
    print("-" * 60)
    print("  清理上一次演示数据：")
    for table, count in cleaned.items():
        if count > 0:
            print(f"    · {table:<20} 删除 {count} 条")
    print("  创建新演示数据：")
    for table, count in created.items():
        print(f"    · {table:<20} 新建 {count} 条")
    print("-" * 60 + "\n")


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
