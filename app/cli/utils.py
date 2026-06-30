"""CLI 共享工具：异步运行、表格输出、密码交互、数据库会话。"""
from __future__ import annotations

import asyncio
import hashlib
import getpass
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncSessionLocal

console = Console()


def run_async(coro: Awaitable[Any]) -> Any:
    """在同步 CLI 中运行异步协程。"""
    return asyncio.run(coro)


@asynccontextmanager
async def db_session() -> AsyncIterator[AsyncSession]:
    """提供异步数据库会话上下文（CLI 专用，自动提交）。"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def blake2b_prehash_interactive(prompt: str = "密码") -> str:
    """交互式输入密码并做 BLAKE2b 预哈希（与前端流程一致）。

    用于 CLI 创建/修改密码场景，保证与 Web 端密码哈希链路一致：
    原始密码 → BLAKE2b 预哈希 → Argon2id 慢哈希。
    """
    pw = getpass.getpass(f"{prompt}: ")
    pw2 = getpass.getpass(f"确认{prompt}: ")
    if pw != pw2:
        raise typer.BadParameter("两次输入的密码不一致")
    if len(pw) < 8:
        raise typer.BadParameter("密码至少 8 位")
    # BLAKE2b 预哈希（与前端一致，防 DoS 截断）
    return hashlib.blake2b(pw.encode(), digest_size=64).hexdigest()


def print_table(title: str, columns: list[str], rows: list[list[Any]]) -> None:
    """用 rich 输出对齐表格。"""
    table = Table(title=title, show_lines=False)
    for col in columns:
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(*[str(c) for c in row])
    console.print(table)


def confirm(message: str, default: bool = False) -> bool:
    """危险操作确认。"""
    return typer.confirm(message, default=default)


def success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def error(message: str) -> None:
    console.print(f"[red]✗[/red] {message}")


def info(message: str) -> None:
    console.print(f"[cyan]ℹ[/cyan] {message}")


def warn(message: str) -> None:
    console.print(f"[yellow]![/yellow] {message}")
