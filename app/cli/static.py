"""静态资源收集与密钥生成命令。

用法：
    2c2a collectstatic [dest]       # 收集静态文件到指定目录
    2c2a keys generate              # 生成所有密钥（Ed25519/AES/BLAKE2b/SECRET_KEY）
    2c2a keys ed25519               # 仅生成 Ed25519 密钥对
    2c2a keys aes                   # 仅生成 AES-GCM 主密钥
    2c2a keys blake2b               # 仅生成 keyed-BLAKE2b 签名密钥
    2c2a keys secret                # 仅生成 SECRET_KEY
    2c2a keys show                  # 显示当前已加载的密钥配置状态
"""
from __future__ import annotations

import base64
import os
import secrets
import shutil
from pathlib import Path

import typer

from app.cli.utils import console, error, info, success, warn
from app.core.config import settings

# keys 作为顶层命令组导出
keys_app = typer.Typer(help="密钥生成", no_args_is_help=True)


def collectstatic(
    destination: str = typer.Argument(
        None, help="目标目录（默认 staticfiles/）"
    ),
    clear: bool = typer.Option(False, "--clear", "-c", help="先清空目标目录"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅显示将复制哪些文件"),
):
    """收集所有静态文件到指定目录（供 Nginx/CDN 直接服务）。

    收集来源：
    - app/static/（应用自带静态资源）
    - 各插件目录下的 static/（插件静态资源，如有）
    """
    dest = Path(destination) if destination else Path("staticfiles")
    src = Path(__file__).resolve().parent.parent / "static"

    if not src.is_dir():
        error(f"静态资源源目录不存在: {src}")
        raise typer.Exit(1)

    if dry_run:
        info(f"[dry-run] 将复制 {src} → {dest}")
        for f in src.rglob("*"):
            if f.is_file():
                console.print(f"  {f.relative_to(src)}")
        return

    if dest.exists():
        if clear:
            warn(f"清空目标目录: {dest}")
            shutil.rmtree(dest)
        else:
            error(f"目标目录已存在: {dest}（使用 --clear 清空后重试）")
            raise typer.Exit(1)

    dest.mkdir(parents=True)

    # 复制应用静态资源
    copied = 0
    for f in src.rglob("*"):
        if f.is_file():
            rel = f.relative_to(src)
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            copied += 1

    # 复制插件静态资源（app/plugins/*/static/）
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugin_copied = 0
    for plugin_static in plugins_dir.glob("*/static"):
        if plugin_static.is_dir():
            plugin_id = plugin_static.parent.name
            target_dir = dest / "plugins" / plugin_id
            target_dir.mkdir(parents=True, exist_ok=True)
            for f in plugin_static.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(plugin_static)
                    target = target_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    plugin_copied += 1

    success(f"已收集 {copied} 个应用静态文件 → {dest}")
    if plugin_copied:
        success(f"已收集 {plugin_copied} 个插件静态文件 → {dest}/plugins/")


# ───────────────────────── 密钥生成 ─────────────────────────


@keys_app.command("generate")
def generate_all():
    """生成所有密钥（输出 .env 格式，可追加到 .env 文件）。"""
    console.print("\n[bold]生成所有密钥（.env 格式）[/bold]\n")
    _print_secret_key()
    _print_aes_key()
    _print_blake2b_key()
    _print_ed25519_keys()
    console.print("\n[dim]将以上内容追加到 .env 文件即可使用[/dim]")


@keys_app.command("secret")
def gen_secret():
    """生成 SECRET_KEY。"""
    _print_secret_key()


@keys_app.command("aes")
def gen_aes():
    """生成 AES-GCM 主密钥（32 字节 base64）。"""
    _print_aes_key()


@keys_app.command("blake2b")
def gen_blake2b():
    """生成 keyed-BLAKE2b 缓存签名密钥。"""
    _print_blake2b_key()


@keys_app.command("ed25519")
def gen_ed25519():
    """生成 Ed25519 密钥对（用于 JWT 签名）。"""
    _print_ed25519_keys()


@keys_app.command("show")
def show_keys():
    """显示当前已加载的密钥配置状态（不显示密钥本身）。"""
    console.print("\n[bold]密钥配置状态[/bold]\n")
    items = [
        ("SECRET_KEY", bool(settings.secret_key), "通用密钥"),
        ("ED25519_PRIVATE_KEY_PEM", bool(settings.ed25519_private_key_pem), "JWT 签名私钥"),
        ("ED25519_PUBLIC_KEY_PEM", bool(settings.ed25519_public_key_pem), "JWT 验签公钥"),
        ("CRYPTO_MASTER_KEY_B64", bool(settings.crypto_master_key_b64), "AES-GCM 主密钥"),
        ("CACHE_SIGNING_KEY", bool(settings.cache_signing_key), "BLAKE2b 缓存签名密钥"),
    ]
    for name, configured, desc in items:
        status = "[green]✓ 已配置[/green]" if configured else "[red]✗ 未配置[/red]"
        console.print(f"  {status:30s} {name:30s} [dim]{desc}[/dim]")

    if settings.is_prod:
        missing = [n for n, c, _ in items if not c]
        if missing:
            console.print(f"\n[red]⚠ 生产环境缺少必需密钥: {', '.join(missing)}[/red]")
        else:
            console.print("\n[green]✓ 所有密钥已就绪[/green]")
    else:
        console.print("\n[dim]开发模式：未配置的密钥将从 SECRET_KEY 自动派生[/dim]")


def _print_secret_key():
    key = secrets.token_urlsafe(48)
    console.print(f"[cyan]# SECRET_KEY（通用密钥）[/cyan]")
    console.print(f"SECRET_KEY={key}\n")


def _print_aes_key():
    key = base64.b64encode(os.urandom(32)).decode()
    console.print(f"[cyan]# CRYPTO_MASTER_KEY_B64（AES-256-GCM 主密钥，32 字节 base64）[/cyan]")
    console.print(f"CRYPTO_MASTER_KEY_B64={key}\n")


def _print_blake2b_key():
    key = secrets.token_urlsafe(32)
    console.print(f"[cyan]# CACHE_SIGNING_KEY（keyed-BLAKE2b 缓存签名密钥）[/cyan]")
    console.print(f"CACHE_SIGNING_KEY={key}\n")


def _print_ed25519_keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    k = Ed25519PrivateKey.generate()
    priv = k.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = k.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    console.print(f"[cyan]# ED25519 密钥对（JWT 签名/验签）[/cyan]")
    console.print("ED25519_PRIVATE_KEY_PEM=\"\"\"")
    console.print(priv, end="")
    console.print('"""')
    console.print("ED25519_PUBLIC_KEY_PEM=\"\"\"")
    console.print(pub, end="")
    console.print('"""')
