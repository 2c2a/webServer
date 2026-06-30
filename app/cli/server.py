"""服务器启动命令。

用法：
    2c2a serve                      # 启动 Granian ASGI 服务器
    2c2a serve --reload             # 开发模式（热重载）
    2c2a serve --workers 4          # 多 worker
    2c2a worker                     # 启动 RedisHuey 任务消费者
    2c2a shell                      # 启动交互式 Python shell（预加载 app 上下文）
"""
from __future__ import annotations

import code
import subprocess
import sys

import typer

from app.cli.utils import info, success, warn
from app.core.config import settings

server_app = typer.Typer(help="服务器与运行时", no_args_is_help=True)


@server_app.command("serve")
def serve(
    host: str = typer.Option(None, "--host", "-h", help="监听地址（默认 0.0.0.0）"),
    port: int = typer.Option(None, "--port", "-p", help="监听端口（默认 8000）"),
    workers: int = typer.Option(None, "--workers", "-w", help="worker 数量"),
    reload: bool = typer.Option(False, "--reload", help="开发模式热重载"),
    interface: str = typer.Option("asgi", "--interface", help="ASGI/RSGI/WSGI"),
    with_worker: bool = typer.Option(
        False, "--with-worker", help="同时启动 Huey 消费者（开发模式推荐）"
    ),
):
    """启动 Granian ASGI 服务器。"""
    host = host or settings.host
    port = port or settings.port
    workers = workers or settings.workers

    # 检查 immediate 模式
    from app.tasks.huey_app import huey

    if huey.immediate:
        warn("Huey 处于 immediate 模式：任务将在 web 进程内同步执行（不隔离）")
        warn("建议使用 --with-worker 或单独运行 2c2a serve worker")
    elif with_worker:
        info("将同时启动 Huey 消费者进程")

    cmd = [
        sys.executable,
        "-m",
        "granian",
        "--interface",
        interface,
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
        warn("开发模式：热重载已启用")
    else:
        cmd.extend(["--workers", str(workers)])

    info(f"启动 Granian: {host}:{port} ({workers} workers, {interface})")
    info(f"命令: {' '.join(cmd)}")

    worker_proc = None
    if with_worker and not huey.immediate:
        worker_cmd = [
            sys.executable,
            "-m",
            "huey.bin.huey_consumer",
            "app.tasks.huey_app.huey",
            "--workers",
            "1",
        ]
        info(f"同时启动 Huey 消费者: {' '.join(worker_cmd)}")
        worker_proc = subprocess.Popen(worker_cmd)

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        warn("服务器已停止")
    except FileNotFoundError:
        typer.secho(
            "未找到 granian，请安装: pip install granian",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    finally:
        if worker_proc is not None:
            worker_proc.terminate()
            try:
                worker_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker_proc.kill()


@server_app.command("worker")
def worker(
    workers: int = typer.Option(1, "--workers", "-w", help="消费者进程数"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细日志"),
):
    """启动 RedisHuey 任务消费者（处理后台 WinRM 操作等异步任务）。"""
    cmd = [
        sys.executable,
        "-m",
        "huey.bin.huey_consumer",
        "app.tasks.huey_app.huey",
        "--workers",
        str(workers),
    ]
    if verbose:
        cmd.append("-v")

    info(f"启动 Huey 消费者 ({workers} workers)")
    info(f"命令: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        warn("消费者已停止")
    except FileNotFoundError:
        typer.secho(
            "未找到 huey_consumer，请安装: pip install huey[redis]",
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)


@server_app.command("shell")
def shell():
    """启动交互式 Python shell（预加载应用上下文）。"""
    import app  # noqa: F401
    from app.core.config import settings as _settings
    from app.core.db import AsyncSessionLocal as _Session
    from app.models import Base as _Base
    from app.models import User as _User

    banner = (
        "2c2a 交互式 Shell\n"
        "已预加载：app, settings, AsyncSessionLocal, Base, User\n"
        "异步操作请用 asyncio.run() 包装。"
    )
    namespace = {
        "app": app,
        "settings": _settings,
        "AsyncSessionLocal": _Session,
        "Base": _Base,
        "User": _User,
        "asyncio": __import__("asyncio"),
    }
    code.interact(banner=banner, local=namespace)


@server_app.command("check")
def check():
    """检查配置与依赖是否就绪。"""
    from app.cli.utils import console

    console.print("\n[bold]配置检查[/bold]")

    # 环境检查
    checks = []

    # 1. 密钥检查
    if settings.is_prod:
        checks.append(("SECRET_KEY", bool(settings.secret_key)))
        checks.append(("ED25519 私钥", bool(settings.ed25519_private_key_pem)))
        checks.append(("ED25519 公钥", bool(settings.ed25519_public_key_pem)))
        checks.append(("AES-GCM 主密钥", bool(settings.crypto_master_key_b64)))
        checks.append(("缓存签名密钥", bool(settings.cache_signing_key)))
    else:
        checks.append(("开发模式密钥", True))

    checks.append(("数据库引擎", settings.db_engine != ""))
    checks.append(("Redis 启用", settings.redis_enabled))

    for name, ok in checks:
        status = "[green]✓[/green]" if ok else "[red]✗[/red]"
        console.print(f"  {status} {name}")

    # 2. 数据库连接检查
    console.print("\n[bold]数据库连接[/bold]")
    import asyncio

    async def _check_db():
        from app.core.db import engine

        try:
            async with engine.connect() as conn:
                await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            await engine.dispose()
            return True
        except Exception as e:  # noqa: BLE001
            console.print(f"  [red]✗[/red] 数据库连接失败: {e}")
            return False

    if asyncio.run(_check_db()):
        console.print("  [green]✓[/green] 数据库连接正常")

    # 3. Redis 连接检查
    if settings.redis_enabled:
        console.print("\n[bold]Redis 连接[/bold]")
        try:
            from app.core.redis import get_redis

            async def _check_redis():
                r = await get_redis()
                await r.ping()
                await r.aclose()

            asyncio.run(_check_redis())
            console.print("  [green]✓[/green] Redis 连接正常")
        except Exception as e:  # noqa: BLE001
            console.print(f"  [red]✗[/red] Redis 连接失败: {e}")

    console.print()
    success("检查完成")
