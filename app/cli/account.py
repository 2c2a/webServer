"""账户管理命令。

用法：
    2c2a account createsuperuser              # 创建超级管理员
    2c2a account create                       # 创建普通用户
    2c2a account list                         # 列出用户
    2c2a account changepassword <username>    # 修改密码
    2c2a account activate <username>          # 启用账号
    2c2a account deactivate <username>        # 禁用账号
    2c2a account ban <username>               # 封禁账号（递增 ban_version）
    2c2a account unban <username>             # 解封
    2c2a account promote <username>           # 提升为 staff
    2c2a account demote <username>            # 取消 staff
    2c2a account delete <username>            # 删除账号
"""
from __future__ import annotations

from datetime import datetime, timezone

import typer
from sqlalchemy import select

from app.cli.utils import (
    blake2b_prehash_interactive,
    confirm,
    db_session,
    error,
    print_table,
    run_async,
    success,
    warn,
)
from app.models.user import User, UserBan, UserProfile
from app.security.password import hash_password

account_app = typer.Typer(help="账户管理", no_args_is_help=True)


async def _get_user_by_username(session, username: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


@account_app.command("createsuperuser")
def create_superuser(
    username: str = typer.Option(..., "--username", "-u", help="用户名"),
    email: str = typer.Option(None, "--email", "-e", help="邮箱"),
    password: str = typer.Option(None, "--password", "-p", help="密码（不传则交互输入）"),
):
    """创建超级管理员。"""
    _create_user(
        username=username,
        email=email,
        password=password,
        is_superuser=True,
        is_staff=True,
        is_verified=True,
        label="超级管理员",
    )


@account_app.command("create")
def create_user(
    username: str = typer.Option(..., "--username", "-u", help="用户名"),
    email: str = typer.Option(None, "--email", "-e", help="邮箱"),
    password: str = typer.Option(None, "--password", "-p", help="密码（不传则交互输入）"),
    staff: bool = typer.Option(False, "--staff", help="赋予 staff 权限"),
):
    """创建普通用户。"""
    _create_user(
        username=username,
        email=email,
        password=password,
        is_superuser=False,
        is_staff=staff,
        is_verified=False,
        label="用户",
    )


def _create_user(
    username: str,
    email: str | None,
    password: str | None,
    is_superuser: bool,
    is_staff: bool,
    is_verified: bool,
    label: str,
) -> None:
    # 密码处理：交互输入或命令行传入
    if password:
        if len(password) < 8:
            error("密码至少 8 位")
            raise typer.Exit(1)
        import hashlib

        prehash = hashlib.blake2b(password.encode(), digest_size=64).hexdigest()
    else:
        prehash = blake2b_prehash_interactive("密码")

    async def _do():
        async with db_session() as session:
            existing = await _get_user_by_username(session, username)
            if existing is not None:
                error(f"用户名 {username} 已存在")
                raise typer.Exit(1)
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(prehash),
                is_active=True,
                is_staff=is_staff,
                is_superuser=is_superuser,
                is_verified=is_verified,
            )
            session.add(user)
            await session.flush()
            session.add(UserProfile(user_id=user.id))
            return user.id

    user_id = run_async(_do())
    success(f"{label}已创建: {username} (id={user_id})")


@account_app.command("list")
def list_users(
    staff: bool = typer.Option(False, "--staff", help="仅显示 staff"),
    superuser: bool = typer.Option(False, "--superuser", help="仅显示超管"),
    active: bool = typer.Option(False, "--active", help="仅显示启用"),
    limit: int = typer.Option(100, "--limit", "-n", help="最多显示数量"),
):
    """列出用户。"""
    from sqlalchemy import or_

    async def _do():
        async with db_session() as session:
            stmt = select(User)
            if staff:
                stmt = stmt.where(User.is_staff == True)  # noqa: E712
            if superuser:
                stmt = stmt.where(User.is_superuser == True)  # noqa: E712
            if active:
                stmt = stmt.where(User.is_active == True)  # noqa: E712
            stmt = stmt.order_by(User.id).limit(limit)
            result = await session.execute(stmt)
            return result.scalars().all()

    users = run_async(_do())
    rows = [
        [
            u.id,
            u.username,
            u.email or "-",
            "✓" if u.is_active else "✗",
            "✓" if u.is_staff else "-",
            "✓" if u.is_superuser else "-",
            u.ban_version,
            u.date_joined.strftime("%Y-%m-%d %H:%M") if u.date_joined else "-",
        ]
        for u in users
    ]
    print_table(
        f"用户列表（共 {len(users)} 个）",
        ["ID", "用户名", "邮箱", "启用", "Staff", "超管", "BanVer", "注册时间"],
        rows,
    )


@account_app.command("changepassword")
def change_password(
    username: str = typer.Argument(..., help="用户名"),
    password: str = typer.Option(None, "--password", "-p", help="新密码（不传则交互输入）"),
):
    """修改用户密码。"""
    if password:
        if len(password) < 8:
            error("密码至少 8 位")
            raise typer.Exit(1)
        import hashlib

        prehash = hashlib.blake2b(password.encode(), digest_size=64).hexdigest()
    else:
        prehash = blake2b_prehash_interactive("新密码")

    async def _do():
        async with db_session() as session:
            user = await _get_user_by_username(session, username)
            if user is None:
                error(f"用户 {username} 不存在")
                raise typer.Exit(1)
            user.password_hash = hash_password(prehash)
            # 修改密码后递增 ban_version，使旧令牌失效
            user.ban_version += 1

    run_async(_do())
    success(f"已修改 {username} 的密码（旧令牌已失效）")


@account_app.command("activate")
def activate(username: str = typer.Argument(..., help="用户名")):
    """启用账号。"""
    _set_flag(username, is_active=True, msg="已启用")


@account_app.command("deactivate")
def deactivate(username: str = typer.Argument(..., help="用户名")):
    """禁用账号。"""
    _set_flag(username, is_active=False, msg="已禁用", bump_ban=True)


@account_app.command("promote")
def promote(username: str = typer.Argument(..., help="用户名")):
    """提升为 staff（管理员）。"""
    _set_flag(username, is_staff=True, msg="已提升为 staff")


@account_app.command("demote")
def demote(username: str = typer.Argument(..., help="用户名")):
    """取消 staff 权限。"""
    _set_flag(username, is_staff=False, msg="已取消 staff")


@account_app.command("superuser")
def set_superuser(
    username: str = typer.Argument(..., help="用户名"),
    revoke: bool = typer.Option(False, "--revoke", help="取消超管权限"),
):
    """授予/取消超级管理员权限。"""
    _set_flag(
        username,
        is_superuser=not revoke,
        msg="已取消超管" if revoke else "已授予超管",
    )


def _set_flag(
    username: str,
    *,
    is_active: bool | None = None,
    is_staff: bool | None = None,
    is_superuser: bool | None = None,
    msg: str,
    bump_ban: bool = False,
) -> None:
    async def _do():
        async with db_session() as session:
            user = await _get_user_by_username(session, username)
            if user is None:
                error(f"用户 {username} 不存在")
                raise typer.Exit(1)
            if is_active is not None:
                user.is_active = is_active
            if is_staff is not None:
                user.is_staff = is_staff
            if is_superuser is not None:
                user.is_superuser = is_superuser
            if bump_ban:
                user.ban_version += 1

    run_async(_do())
    success(f"{username} {msg}")


@account_app.command("ban")
def ban_user(
    username: str = typer.Argument(..., help="用户名"),
    reason: str = typer.Option("管理员封禁", "--reason", "-r", help="封禁原因"),
):
    """封禁账号（递增 ban_version，所有令牌立即失效）。"""
    from sqlalchemy.orm import selectinload

    async def _do():
        async with db_session() as session:
            result = await session.execute(
                select(User).options(selectinload(User.active_ban)).where(User.username == username)
            )
            user = result.scalar_one_or_none()
            if user is None:
                error(f"用户 {username} 不存在")
                raise typer.Exit(1)
            # 创建/更新封禁记录
            if user.active_ban is None:
                session.add(UserBan(user_id=user.id, reason=reason))
            else:
                user.active_ban.reason = reason
            user.is_active = False
            user.ban_version += 1  # 无状态秒级令牌撤销

    run_async(_do())
    warn(f"已封禁 {username}（原因：{reason}），所有令牌已失效")


@account_app.command("unban")
def unban_user(username: str = typer.Argument(..., help="用户名")):
    """解封账号。"""
    from sqlalchemy import delete

    async def _do():
        async with db_session() as session:
            user = await _get_user_by_username(session, username)
            if user is None:
                error(f"用户 {username} 不存在")
                raise typer.Exit(1)
            # 删除封禁记录
            await session.execute(delete(UserBan).where(UserBan.user_id == user.id))
            user.is_active = True

    run_async(_do())
    success(f"已解封 {username}")


@account_app.command("delete")
def delete_user(
    username: str = typer.Argument(..., help="用户名"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
):
    """删除账号（级联删除关联数据）。"""
    if not yes and not confirm(f"⚠️  确认删除用户 {username}？此操作不可恢复"):
        raise typer.Abort()

    async def _do():
        async with db_session() as session:
            user = await _get_user_by_username(session, username)
            if user is None:
                error(f"用户 {username} 不存在")
                raise typer.Exit(1)
            await session.delete(user)

    run_async(_do())
    warn(f"已删除用户 {username}")


@account_app.command("info")
def user_info(username: str = typer.Argument(..., help="用户名")):
    """查看用户详情。"""
    async def _do():
        async with db_session() as session:
            from sqlalchemy.orm import selectinload

            result = await session.execute(
                select(User).options(selectinload(User.active_ban)).where(User.username == username)
            )
            user = result.scalar_one_or_none()
            if user is None:
                error(f"用户 {username} 不存在")
                raise typer.Exit(1)
            # 在会话内预加载所有需要的属性，避免 DetachedInstanceError
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "phone": user.phone,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "is_verified": user.is_verified,
                "ban_version": user.ban_version,
                "date_joined": user.date_joined,
                "last_login": user.last_login,
                "last_login_ip": user.last_login_ip,
                "ban_reason": user.active_ban.reason if user.active_ban else None,
            }

    data = run_async(_do())
    from app.cli.utils import console

    console.print(f"\n[bold]用户详情[/bold]")
    console.print(f"  ID:         {data['id']}")
    console.print(f"  用户名:     {data['username']}")
    console.print(f"  邮箱:       {data['email'] or '-'}")
    console.print(f"  电话:       {data['phone'] or '-'}")
    console.print(f"  启用:       {'✓' if data['is_active'] else '✗'}")
    console.print(f"  Staff:      {'✓' if data['is_staff'] else '-'}")
    console.print(f"  超管:       {'✓' if data['is_superuser'] else '-'}")
    console.print(f"  已验证:     {'✓' if data['is_verified'] else '✗'}")
    console.print(f"  Ban版本:    {data['ban_version']}")
    console.print(f"  注册时间:   {data['date_joined']}")
    console.print(f"  最后登录:   {data['last_login'] or '-'}")
    console.print(f"  最后登录IP: {data['last_login_ip'] or '-'}")
    if data["ban_reason"]:
        console.print(f"  [red]封禁中[/red]: {data['ban_reason']}")
