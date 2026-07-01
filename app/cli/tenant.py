"""租户（站点组）管理命令。

用法：
    2c2a tenant list                       # 列出所有站点组
    2c2a tenant create <name>              # 创建站点组
    2c2a tenant info <slug>                # 查看站点组详情
    2c2a tenant add-hostname <slug> <host> # 绑定域名
    2c2a tenant remove-hostname <host>     # 解绑域名
    2c2a tenant add-admin <slug> <user>    # 添加站点组管理员
    2c2a tenant remove-admin <slug> <user> # 移除站点组管理员
    2c2a tenant activate <slug>            # 激活站点组
    2c2a tenant deactivate <slug>          # 停用站点组
    2c2a tenant config <slug>              # 查看/修改站点组配置
    2c2a tenant invalidate-cache           # 清除租户解析缓存
"""
from __future__ import annotations

import typer
from sqlalchemy import delete, select

from app.cli.utils import (
    console,
    db_session,
    error,
    info,
    print_table,
    run_async,
    success,
    warn,
)
from app.models.tenant import SiteGroup, SiteGroupConfig, SiteGroupHostname
from app.models.user import User

tenant_app = typer.Typer(help="租户（站点组）管理", no_args_is_help=True)


async def _get_by_slug(session, slug: str) -> SiteGroup | None:
    result = await session.execute(select(SiteGroup).where(SiteGroup.slug == slug))
    return result.scalar_one_or_none()


async def _get_by_name(session, name: str) -> SiteGroup | None:
    result = await session.execute(select(SiteGroup).where(SiteGroup.name == name))
    return result.scalar_one_or_none()


async def _get_user(session, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


@tenant_app.command("list")
def list_tenants():
    """列出所有站点组。"""
    async def _do():
        async with db_session() as session:
            result = await session.execute(select(SiteGroup).order_by(SiteGroup.id))
            groups = result.scalars().all()
            rows = []
            for g in groups:
                # 统计域名数
                host_result = await session.execute(
                    select(SiteGroupHostname).where(SiteGroupHostname.site_group_id == g.id)
                )
                host_count = len(host_result.scalars().all())
                rows.append([
                    g.id,
                    g.name,
                    g.slug,
                    "✓" if g.is_active else "✗",
                    g.site_name or "-",
                    host_count,
                    len(g.admins),
                ])
            return rows

    rows = run_async(_do())
    print_table(
        f"站点组列表（共 {len(rows)} 个）",
        ["ID", "名称", "Slug", "启用", "站点名", "域名数", "管理员数"],
        rows,
    )


@tenant_app.command("create")
def create_tenant(
    name: str = typer.Argument(..., help="站点组名称"),
    slug: str = typer.Option(None, "--slug", "-s", help="Slug（默认自动生成）"),
    site_name: str = typer.Option(None, "--site-name", help="站点显示名"),
    description: str = typer.Option("", "--desc", "-d", help="描述"),
    is_demo: bool = typer.Option(False, "--demo", help="标记为演示站点（单站点 demo）"),
):
    """创建站点组。"""
    import re

    if not slug:
        # 尝试从名称生成 slug（仅保留 a-z0-9-），无法生成则用随机串
        slug = re.sub(r"[^a-zA-Z0-9-]", "-", name.lower()).strip("-")
        if not slug:
            import secrets

            slug = f"site-{secrets.token_hex(4)}"
    if not re.match(r"^[a-z0-9-]+$", slug):
        error("slug 只能包含小写字母、数字、连字符")
        raise typer.Exit(1)

    async def _do():
        async with db_session() as session:
            existing = await _get_by_slug(session, slug)
            if existing:
                error(f"slug {slug} 已存在")
                raise typer.Exit(1)
            sg = SiteGroup(
                name=name,
                slug=slug,
                site_name=site_name or name,
                description=description,
                is_active=True,
                is_demo=is_demo,
            )
            session.add(sg)
            await session.flush()
            # 创建空配置覆盖
            session.add(SiteGroupConfig(site_group_id=sg.id))
            return sg.id

    sg_id = run_async(_do())
    demo_tag = " [DEMO]" if is_demo else ""
    success(f"站点组已创建{demo_tag}: {name} (slug={slug}, id={sg_id})")


@tenant_app.command("info")
def tenant_info(slug: str = typer.Argument(..., help="站点组 slug")):
    """查看站点组详情。"""
    async def _do():
        async with db_session() as session:
            sg = await _get_by_slug(session, slug)
            if sg is None:
                error(f"站点组 {slug} 不存在")
                raise typer.Exit(1)
            # 域名列表
            host_result = await session.execute(
                select(SiteGroupHostname).where(SiteGroupHostname.site_group_id == sg.id)
            )
            hostnames = host_result.scalars().all()
            return sg, hostnames

    sg, hostnames = run_async(_do())
    console.print(f"\n[bold]站点组详情[/bold]")
    console.print(f"  ID:       {sg.id}")
    console.print(f"  名称:     {sg.name}")
    console.print(f"  Slug:     {sg.slug}")
    console.print(f"  启用:     {'✓' if sg.is_active else '✗'}")
    console.print(f"  站点名:   {sg.site_name or '-'}")
    console.print(f"  描述:     {sg.description or '-'}")
    console.print(f"  管理员:   {', '.join(u.username for u in sg.admins) or '-'}")
    console.print(f"  成员数:   {len(sg.members)}")
    console.print(f"\n  [bold]绑定域名（{len(hostnames)}）:[/bold]")
    for h in hostnames:
        console.print(f"    • {h.hostname}")


@tenant_app.command("add-hostname")
def add_hostname(
    slug: str = typer.Argument(..., help="站点组 slug"),
    hostname: str = typer.Argument(..., help="要绑定的域名（如 example.com）"),
):
    """绑定域名到站点组。"""
    hostname = hostname.lower().strip()

    async def _do():
        async with db_session() as session:
            sg = await _get_by_slug(session, slug)
            if sg is None:
                error(f"站点组 {slug} 不存在")
                raise typer.Exit(1)
            # 检查域名是否已绑定
            existing = await session.execute(
                select(SiteGroupHostname).where(SiteGroupHostname.hostname == hostname)
            )
            if existing.scalar_one_or_none():
                error(f"域名 {hostname} 已绑定到其他站点组")
                raise typer.Exit(1)
            session.add(SiteGroupHostname(hostname=hostname, site_group_id=sg.id))
            return sg.name

    name = run_async(_do())
    # 清除缓存
    run_async(_invalidate(hostname))
    success(f"域名 {hostname} 已绑定到站点组 {name}")


@tenant_app.command("remove-hostname")
def remove_hostname(hostname: str = typer.Argument(..., help="要解绑的域名")):
    """解绑域名。"""
    hostname = hostname.lower().strip()

    async def _do():
        async with db_session() as session:
            result = await session.execute(
                select(SiteGroupHostname).where(SiteGroupHostname.hostname == hostname)
            )
            h = result.scalar_one_or_none()
            if h is None:
                error(f"域名 {hostname} 未绑定")
                raise typer.Exit(1)
            await session.delete(h)

    run_async(_do())
    run_async(_invalidate(hostname))
    success(f"域名 {hostname} 已解绑")


@tenant_app.command("add-admin")
def add_admin(
    slug: str = typer.Argument(..., help="站点组 slug"),
    username: str = typer.Argument(..., help="用户名"),
):
    """添加站点组管理员。"""
    async def _do():
        async with db_session() as session:
            sg = await _get_by_slug(session, slug)
            if sg is None:
                error(f"站点组 {slug} 不存在")
                raise typer.Exit(1)
            user = await _get_user(session, username)
            if user is None:
                error(f"用户 {username} 不存在")
                raise typer.Exit(1)
            if user not in sg.admins:
                sg.admins.append(user)

    run_async(_do())
    success(f"{username} 已成为站点组 {slug} 的管理员")


@tenant_app.command("remove-admin")
def remove_admin(
    slug: str = typer.Argument(..., help="站点组 slug"),
    username: str = typer.Argument(..., help="用户名"),
):
    """移除站点组管理员。"""
    async def _do():
        async with db_session() as session:
            sg = await _get_by_slug(session, slug)
            if sg is None:
                error(f"站点组 {slug} 不存在")
                raise typer.Exit(1)
            user = await _get_user(session, username)
            if user and user in sg.admins:
                sg.admins.remove(user)

    run_async(_do())
    success(f"{username} 已移出站点组 {slug} 的管理员")


@tenant_app.command("activate")
def activate_tenant(slug: str = typer.Argument(..., help="站点组 slug")):
    """激活站点组。"""
    _set_active(slug, True)


@tenant_app.command("deactivate")
def deactivate_tenant(slug: str = typer.Argument(..., help="站点组 slug")):
    """停用站点组。"""
    _set_active(slug, False)


def _set_active(slug: str, active: bool):
    async def _do():
        async with db_session() as session:
            sg = await _get_by_slug(session, slug)
            if sg is None:
                error(f"站点组 {slug} 不存在")
                raise typer.Exit(1)
            sg.is_active = active

    run_async(_do())
    success(f"站点组 {slug} 已{'激活' if active else '停用'}")


@tenant_app.command("invalidate-cache")
def invalidate_cache(
    hostname: str = typer.Option(None, "--hostname", "-h", help="仅清除指定域名的缓存"),
):
    """清除租户解析缓存（域名 → 站点组）。"""
    if hostname:
        run_async(_invalidate(hostname.lower().strip()))
        success(f"已清除 {hostname} 的租户缓存")
    else:
        from app.core.config import settings
        from app.core.redis import get_redis

        async def _clear_all():
            if not settings.redis_enabled:
                warn("Redis 未启用，无缓存可清除")
                return 0
            r = await get_redis()
            count = 0
            async for key in r.scan_iter(match="tenant:host:*", count=100):
                await r.delete(key)
                count += 1
            await r.aclose()
            return count

        count = run_async(_clear_all())
        success(f"已清除 {count} 个租户缓存键")


async def _invalidate(hostname: str):
    from app.tenant.resolver import invalidate_tenant_cache

    await invalidate_tenant_cache(hostname)
