#!/usr/bin/env python3
"""
2c2a 启动脚本

启动 FastAPI Web 服务器
"""

import sys
import os
import argparse


def main():
    parser = argparse.ArgumentParser(description="2c2a 云电脑管理平台")
    parser.add_argument("command", choices=["web", "worker", "beat", "migrate", "shell"], help="要执行的命令")
    parser.add_argument("--host", default="0.0.0.0", help="Web 服务器绑定地址")
    parser.add_argument("--port", type=int, default=8000, help="Web 服务器端口")
    parser.add_argument("--workers", type=int, default=1, help="Worker 进程数")
    parser.add_argument("--reload", action="store_true", help="启用热重载（开发模式）")
    args = parser.parse_args()

    if args.command == "web":
        _start_web(args)
    elif args.command == "worker":
        _start_worker()
    elif args.command == "beat":
        _start_beat()
    elif args.command == "migrate":
        _run_migrate()
    elif args.command == "shell":
        _start_shell()


def _start_web(args):
    """启动 FastAPI Web 服务器"""
    import uvicorn

    if args.reload:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level="info",
        )
    else:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            workers=args.workers,
            log_level="info",
            access_log=True,
        )


def _start_worker():
    """启动 Huey Worker"""
    from huey.consumer import Consumer
    from app.huey_config import huey

    # 预加载所有任务模块
    import app.tasks  # noqa: F401

    consumer = Consumer(huey, workers=2, worker_type="thread")
    consumer.run()


def _start_beat():
    """启动 Huey Beat（定时任务调度器）"""
    from huey.consumer import Consumer
    from app.huey_config import huey

    import app.tasks  # noqa: F401

    consumer = Consumer(huey, workers=1, worker_type="thread")
    consumer.run()


def _run_migrate():
    """运行数据库迁移"""
    import asyncio
    from app.database import engine, Base

    async def _create_tables():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("数据库表创建完成")

    asyncio.run(_create_tables())


def _start_shell():
    """启动交互式 Shell"""
    import asyncio
    from app.database import async_session_factory

    print("2c2a Shell")
    print("可用变量: async_session_factory, engine")
    print("使用 asyncio.run() 执行异步代码")
    import code
    code.interact(local={
        "async_session_factory": async_session_factory,
        "engine": engine,
        "asyncio": asyncio,
    })


if __name__ == "__main__":
    main()
