"""演示数据管理命令。

用法：
    2c2a demo seed       # 仅预置演示业务数据（不清理，重复执行会叠加）
    2c2a demo clean      # 清理所有演示业务数据
    2c2a demo reset      # 清理 + 重建演示业务数据（推荐）
    2c2a demo accounts   # 预置演示账号（superadmin/siteadmin/user）
"""
from __future__ import annotations

import typer

from app.cli.utils import console, error, run_async, success, warn

demo_app = typer.Typer(help="演示数据管理", no_args_is_help=True)


@demo_app.command("accounts")
def accounts():
    """预置演示账号：superadmin / siteadmin / user（密码 demo123456）。"""
    from app.core.config import settings

    if settings.is_prod:
        error("生产环境禁止预置演示账号")
        raise typer.Exit(1)

    from app.cli.account import seed_demo_accounts

    result = run_async(seed_demo_accounts())
    created = result["created"]
    skipped = result["skipped"]

    console.print()
    console.print("[bold cyan]演示账号[/bold cyan]")
    console.print(f"  新建: {', '.join(created) if created else '无'}")
    console.print(f"  跳过: {', '.join(skipped) if skipped else '无'}")
    console.print()
    warn("密码统一 demo123456，仅用于 demo/开发环境")


@demo_app.command("seed")
def seed():
    """预置演示业务数据（不清理已有数据，重复执行会叠加）。"""
    from app.core.config import settings

    if settings.is_prod:
        error("生产环境禁止预置演示数据")
        raise typer.Exit(1)

    from app.cli.demo_data import seed_demo_business_data

    result = run_async(seed_demo_business_data())
    created = result["created"]

    console.print()
    success("演示业务数据已预置")
    for table, count in created.items():
        console.print(f"  · {table:<20} 新建 {count} 条")


@demo_app.command("clean")
def clean():
    """清理所有演示业务数据（按 [DEMO] 前缀精准删除）。"""
    from app.core.config import settings

    if settings.is_prod:
        error("生产环境禁止操作演示数据")
        raise typer.Exit(1)

    from app.cli.demo_data import clean_demo_business_data

    result = run_async(clean_demo_business_data())
    deleted = result["deleted"]

    console.print()
    success("演示业务数据已清理")
    total = 0
    for table, count in deleted.items():
        if count > 0:
            console.print(f"  · {table:<20} 删除 {count} 条")
            total += count
    console.print(f"  合计删除 {total} 条")


@demo_app.command("reset")
def reset():
    """清理 + 重建演示业务数据（推荐，保证环境干净）。"""
    from app.core.config import settings

    if settings.is_prod:
        error("生产环境禁止操作演示数据")
        raise typer.Exit(1)

    from app.cli.demo_data import reset_demo_business_data

    result = run_async(reset_demo_business_data())
    cleaned = result["cleaned"]["deleted"]
    created = result["seeded"]["created"]

    console.print()
    success("演示业务数据已重置")
    console.print()
    console.print("[bold]清理：[/bold]")
    for table, count in cleaned.items():
        if count > 0:
            console.print(f"  · {table:<20} 删除 {count} 条")
    console.print()
    console.print("[bold]新建：[/bold]")
    for table, count in created.items():
        console.print(f"  · {table:<20} 新建 {count} 条")
