"""数据库迁移命令（基于 Alembic）。

用法：
    2c2a db init              # 初始化数据库（create_all，开发用）
    2c2a db migrate           # 生成迁移脚本（autogenerate）
    2c2a db upgrade [rev]     # 升级到指定版本（默认 head）
    2c2a db downgrade <rev>   # 回滚到指定版本
    2c2a db history           # 查看迁移历史
    2c2a db current           # 查看当前版本
    2c2a db heads             # 查看最新版本
    2c2a db reset             # 危险：重置数据库（drop_all + create_all）
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from app.cli.utils import confirm, error, info, run_async, success, warn

db_app = typer.Typer(help="数据库迁移与管理", no_args_is_help=True)

# Alembic 配置文件路径
_ALEMBIC_INI = str(Path(__file__).resolve().parent.parent.parent / "alembic.ini")


def _run_alembic(*args: str) -> int:
    """执行 alembic 子命令，透传输出。"""
    cmd = [sys.executable, "-m", "alembic", "-c", _ALEMBIC_INI, *args]
    info(f"执行: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    return result.returncode


@db_app.command("init")
def init_db():
    """初始化数据库（直接 create_all + stamp head，开发用）。

    生产环境请使用 ``2c2a db upgrade`` 走 Alembic 迁移。

    注意：``create_all`` 只会创建当前已注册模型对应的表，并标记
    版本为 head。之后新增模型时需用 ``2c2a db migrate -m "..."``
    生成迁移脚本，再 ``2c2a db upgrade`` 应用。
    """
    from app.core.db import engine
    from app.models import Base

    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    run_async(_create())
    success("数据库表已创建（create_all）")

    # 将 alembic_version 标记为 head，避免后续 upgrade 从零开始与已存在表冲突
    rc = _run_alembic("stamp", "head")
    if rc == 0:
        success("已标记当前版本为 head")
    else:
        warn("stamp head 失败，请手动执行 `alembic stamp head`")


@db_app.command("migrate")
def make_migrations(
    message: str = typer.Option(..., "-m", "--message", help="迁移说明"),
    empty: bool = typer.Option(False, "--empty", help="生成空迁移脚本（手动编辑）"),
):
    """生成迁移脚本（autogenerate）。"""
    args = ["revision", "--autogenerate", "-m", message]
    if empty:
        args = ["revision", "-m", message]
    rc = _run_alembic(*args)
    if rc == 0:
        success("迁移脚本已生成")
    else:
        error("迁移脚本生成失败")
        raise typer.Exit(rc)


@db_app.command("upgrade")
def upgrade(
    revision: str = typer.Argument("head", help="目标版本（默认 head）"),
):
    """升级数据库到指定版本。"""
    rc = _run_alembic("upgrade", revision)
    if rc == 0:
        success(f"已升级到 {revision}")
    else:
        raise typer.Exit(rc)


@db_app.command("downgrade")
def downgrade(
    revision: str = typer.Argument(..., help="目标版本（如 -1 回滚一步）"),
):
    """回滚数据库到指定版本。"""
    if not confirm(f"确认回滚到 {revision}？此操作可能丢失数据"):
        raise typer.Abort()
    rc = _run_alembic("downgrade", revision)
    if rc == 0:
        success(f"已回滚到 {revision}")
    else:
        raise typer.Exit(rc)


@db_app.command("history")
def history(
    verbose: bool = typer.Option(False, "-v", "--verbose", help="显示详细信息"),
):
    """查看迁移历史。"""
    args = ["history"]
    if verbose:
        args.append("--verbose")
    _run_alembic(*args)


@db_app.command("current")
def current():
    """查看当前数据库版本。"""
    _run_alembic("current")


@db_app.command("heads")
def heads():
    """查看最新迁移版本。"""
    _run_alembic("heads")


@db_app.command("reset")
def reset_db(
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """危险：重置数据库（drop 所有表 + create_all）。

    仅用于开发环境，生产环境请用迁移。
    """
    if not yes and not confirm("⚠️  这将删除所有数据！确认重置数据库？", default=False):
        raise typer.Abort()
    warn("正在删除所有表...")

    from app.core.db import engine
    from app.models import Base

    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    run_async(_reset())
    success("数据库已重置")

    # 同步 alembic_version 到 head
    rc = _run_alembic("stamp", "head")
    if rc == 0:
        success("已标记当前版本为 head")
    else:
        warn("stamp head 失败，请手动执行 `alembic stamp head`")
