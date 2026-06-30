"""邮件 / SMTP 管理 CLI。

用法：
    2c2a mail check                 # 检查 SMTP 配置状态（全局/站点组）
    2c2a mail test --to user@x.com  # 发送测试邮件
    2c2a mail ping                  # 测试 SMTP 连接（不发送邮件）
    2c2a mail set-password          # 交互式设置全局 SMTP 密码（字段级加密存储）
"""
from __future__ import annotations

import getpass

import typer

from app.cli.utils import console, db_session, error, info, run_async, success
from app.security.field_cipher import encrypt_field

mail_app = typer.Typer(help="邮件 / SMTP 配置与测试", no_args_is_help=True)


def _resolve_smtp_for_cli():
    """CLI 用：解析全局 SMTP 配置（无租户上下文，仅取 SystemConfig）。"""
    from app.services.email import resolve_smtp_config
    from app.tenant.resolver import TenantContext

    async def _do():
        async with db_session() as session:
            # CLI 无请求上下文，用默认租户（site_group_id=None）
            tenant = TenantContext(hostname="", is_default=True)
            return await resolve_smtp_config(session, tenant)

    return run_async(_do())


@mail_app.command("check")
def mail_check():
    """检查 SMTP 配置状态（不显示密码）。"""
    cfg = _resolve_smtp_for_cli()
    from app.services.email import describe_config

    desc = describe_config(cfg)
    console.print("\n[bold]SMTP 配置状态[/bold]\n")
    if not desc.get("enabled"):
        console.print(f"  [red]✗[/red] {desc.get('reason', '邮件发送已禁用')}")
        console.print("\n[dim]提示：设置 EMAIL_ENABLED=true 启用邮件发送[/dim]")
        return

    items = [
        ("已配置完整", "✓" if desc["configured"] else "✗", "green" if desc["configured"] else "red"),
        ("SMTP 主机", f'{desc["host"]}:{desc["port"]}', "white"),
        ("加密方式", desc["encryption"], "white"),
        ("用户名", desc["username"] or "(空)", "white"),
        ("发件邮箱", desc["from_email"] or "(空)", "white"),
        ("发件人名", desc["from_name"] or "(空)", "white"),
        ("已设密码", "是" if desc["has_password"] else "否", "green" if desc["has_password"] else "yellow"),
    ]
    for label, value, color in items:
        console.print(f"  [{color}]{value}[/{color}]  {label}")

    if not desc["configured"]:
        console.print("\n[yellow]⚠ SMTP 未配置完整：缺少 host 或 from_email[/yellow]")
        console.print(
            "[dim]请在管理后台「系统设置」中填写 SMTP 配置，"
            "或使用 `2c2a mail set-password` 设置密码[/dim]"
        )
    else:
        console.print("\n[green]✓ SMTP 配置完整，可使用 `2c2a mail ping` 测试连接[/green]")


@mail_app.command("ping")
def mail_ping():
    """测试 SMTP 连接是否可达（不发送邮件）。"""
    cfg = _resolve_smtp_for_cli()
    if cfg is None:
        error("邮件发送已全局禁用（EMAIL_ENABLED=false）")
        raise typer.Exit(1)
    if not cfg.is_configured:
        error("SMTP 未配置完整（缺少 host 或 from_email）")
        raise typer.Exit(1)

    from app.services.email import test_smtp_connection

    info(f"正在连接 {cfg.host}:{cfg.port}（{cfg.encryption}）...")
    ok, msg = run_async(test_smtp_connection(cfg))
    if ok:
        success(msg)
    else:
        error(msg)
        raise typer.Exit(1)


@mail_app.command("test")
def mail_test(
    to: str = typer.Option(..., "--to", "-t", help="收件人邮箱"),
):
    """发送一封测试邮件到指定地址。"""
    cfg = _resolve_smtp_for_cli()
    if cfg is None:
        error("邮件发送已全局禁用（EMAIL_ENABLED=false）")
        raise typer.Exit(1)
    if not cfg.is_configured:
        error("SMTP 未配置完整（缺少 host 或 from_email）")
        raise typer.Exit(1)

    from app.services.email import send_test_email

    info(f"正在发送测试邮件到 {to} ...")
    result = run_async(send_test_email(cfg, to=to, site_name="2c2a"))
    if result.success:
        success(f"测试邮件已发送（尝试 {result.attempts} 次）")
    else:
        error(f"发送失败：{result.error}")
        raise typer.Exit(1)


@mail_app.command("set-password")
def mail_set_password():
    """交互式设置全局 SMTP 密码（字段级加密存储到 SystemConfig）。

    密码不会以明文存储，使用 AES-256-GCM 字段级加密
    （字段名 system_config.smtp_password）。
    """
    from sqlalchemy import select

    from app.models.tenant import SystemConfig

    pw = getpass.getpass("SMTP 密码: ")
    if not pw:
        error("密码不能为空")
        raise typer.Exit(1)
    pw2 = getpass.getpass("确认密码: ")
    if pw != pw2:
        error("两次输入的密码不一致")
        raise typer.Exit(1)

    async def _do():
        async with db_session() as session:
            result = await session.execute(select(SystemConfig).where(SystemConfig.id == 1))
            cfg = result.scalar_one_or_none()
            if cfg is None:
                # 自动创建单例配置行
                cfg = SystemConfig(id=1)
                session.add(cfg)
            cfg.smtp_password_cipher = encrypt_field(pw, "system_config.smtp_password")

    run_async(_do())
    success("SMTP 密码已加密保存到 SystemConfig.smtp_password_cipher")
    info("提示：密码仅作用于全局 SMTP 配置；站点组密码请在管理后台单独设置")
