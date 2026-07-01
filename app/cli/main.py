"""2c2a CLI 主入口。

用法：
    2c2a --help                    # 查看所有命令
    2c2a db upgrade                # 数据库迁移
    2c2a account createsuperuser   # 创建超管
    2c2a serve                     # 启动服务器
    2c2a plugin list               # 插件管理
    2c2a collectstatic             # 收集静态文件
    2c2a keys generate             # 生成密钥

也可通过 ``python -m app.cli`` 调用。
"""
from __future__ import annotations

import typer
from rich.console import Console

from app.cli.account import account_app
from app.cli.db import db_app
from app.cli.demo import demo_app
from app.cli.mail import mail_app
from app.cli.plugins import plugin_app
from app.cli.server import server_app
from app.cli.static import collectstatic, keys_app
from app.cli.tenant import tenant_app

console = Console()

app = typer.Typer(
    name="2c2a",
    help="2c2a 异步架构管理工具（数据库迁移、账户、服务器、插件、静态资源、密钥、租户）",
    no_args_is_help=True,
    rich_markup_mode="rich",
    add_completion=False,
)


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", help="显示版本号", is_eager=True
    ),
):
    """2c2a 管理工具。"""
    if version:
        from app import __version__

        console.print(f"2c2a v{__version__}")
        raise typer.Exit()


# 注册子命令组
app.add_typer(db_app, name="db", help="数据库迁移与管理")
app.add_typer(account_app, name="account", help="账户管理")
app.add_typer(server_app, name="serve", help="服务器与运行时")
app.add_typer(plugin_app, name="plugin", help="插件管理")
app.add_typer(keys_app, name="keys", help="密钥生成")
app.add_typer(tenant_app, name="tenant", help="租户（站点组）管理")
app.add_typer(mail_app, name="mail", help="邮件 / SMTP 配置与测试")
app.add_typer(demo_app, name="demo", help="演示数据管理（账号/业务数据）")

# 顶层直接命令
app.command(name="collectstatic", help="收集静态文件到指定目录")(collectstatic)


# ── 顶层快捷命令 ──

@app.command("migrate")
def migrate_fast(
    message: str = typer.Option(None, "-m", "--message", help="迁移说明"),
    target: str = typer.Option(None, "--target", help="目标版本（默认 head）"),
):
    """快捷：生成迁移并升级（等同 db migrate + db upgrade）。"""
    from app.cli.db import _run_alembic

    if message:
        rc = _run_alembic("revision", "--autogenerate", "-m", message)
        if rc != 0:
            raise typer.Exit(rc)
    rc = _run_alembic("upgrade", target or "head")
    if rc != 0:
        raise typer.Exit(rc)
    console.print("[green]✓[/green] 迁移完成")


@app.command("createsuperuser")
def createsuperuser_fast(
    username: str = typer.Option(..., "--username", "-u"),
    email: str = typer.Option(None, "--email", "-e"),
    password: str = typer.Option(None, "--password", "-p"),
):
    """快捷：创建超级管理员（等同 account createsuperuser）。"""
    from app.cli.account import _create_user

    _create_user(
        username=username,
        email=email,
        password=password,
        is_superuser=True,
        is_staff=True,
        is_verified=True,
        label="超级管理员",
    )


@app.command("runserver")
def runserver_fast(
    host: str = typer.Option(None, "--host", "-h"),
    port: int = typer.Option(None, "--port", "-p"),
    reload: bool = typer.Option(False, "--reload"),
):
    """快捷：启动开发服务器（等同 serve serve --reload）。"""
    from app.cli.server import serve

    serve(host=host, port=port, workers=1, reload=reload, interface="asgi")


if __name__ == "__main__":
    app()
