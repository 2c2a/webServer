"""
证书文件存储管理

管理 CA 证书和主机证书的文件存储，使用两级目录结构防止目录膨胀。
"""
import logging
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


def _sanitize_path_component(value: str) -> str:
    """过滤非字母数字字符，防止路径穿越"""
    return re.sub(r'[^a-zA-Z0-9]', '', value)


def get_cert_base_dir() -> Path:
    """获取证书存储根目录"""
    settings = get_settings()
    return Path(settings.media_dir) / 'cert_data'


def get_cert_dir(cert_root: str, cert_sub: str) -> Path:
    """获取证书目录路径"""
    return (
        get_cert_base_dir()
        / _sanitize_path_component(cert_root)
        / _sanitize_path_component(cert_sub)
    )


def generate_cert_paths() -> tuple[str, str]:
    """生成随机证书目录路径（两级目录名）"""
    cert_root = secrets.token_hex(1)
    cert_sub = secrets.token_hex(1)
    return cert_root, cert_sub


def generate_ca_paths() -> tuple[str, str]:
    """生成随机 CA 目录路径（两级目录名）"""
    cert_root = secrets.token_hex(1)
    cert_sub = secrets.token_hex(1)
    return cert_root, cert_sub


def get_cert_file_paths(cert_root: str, cert_sub: str) -> dict[str, Path]:
    """获取证书文件路径字典"""
    cert_dir = get_cert_dir(cert_root, cert_sub)
    return {
        'ca_cert': cert_dir / 'ca.crt',
        'client_cert': cert_dir / 'client.crt',
        'client_key': cert_dir / 'client.key',
        'server_pfx': cert_dir / 'server.pfx',
    }


def get_ca_base_dir() -> Path:
    """获取 CA 证书存储根目录"""
    return get_cert_base_dir() / 'ca'


def get_ca_dir(cert_root: str, cert_sub: str) -> Path:
    """获取 CA 证书目录路径"""
    return (
        get_ca_base_dir()
        / _sanitize_path_component(cert_root)
        / _sanitize_path_component(cert_sub)
    )


def get_ca_file_paths(cert_root: str, cert_sub: str) -> dict[str, Path]:
    """获取 CA 文件路径字典"""
    ca_dir = get_ca_dir(cert_root, cert_sub)
    return {
        'key': ca_dir / 'ca.key',
        'cert': ca_dir / 'ca.crt',
    }


def save_cert_files(
    cert_root: str,
    cert_sub: str,
    ca_cert_pem: bytes,
    client_cert_pem: bytes,
    server_pfx_bytes: bytes,
    client_key_pem: Optional[bytes] = None,
) -> Path:
    """
    保存证书文件到磁盘

    返回:
        Path: 证书目录路径
    """
    cert_dir = get_cert_dir(cert_root, cert_sub)
    cert_dir.mkdir(parents=True, exist_ok=True)

    ca_cert_path = cert_dir / 'ca.crt'
    ca_cert_path.write_bytes(ca_cert_pem)
    os.chmod(ca_cert_path, 0o600)

    client_cert_path = cert_dir / 'client.crt'
    client_cert_path.write_bytes(client_cert_pem)
    os.chmod(client_cert_path, 0o600)

    if client_key_pem:
        client_key_path = cert_dir / 'client.key'
        client_key_path.write_bytes(client_key_pem)
        os.chmod(client_key_path, 0o600)

    server_pfx_path = cert_dir / 'server.pfx'
    server_pfx_path.write_bytes(server_pfx_bytes)
    os.chmod(server_pfx_path, 0o600)

    logger.info("证书文件已保存: %s", cert_dir)
    return cert_dir


def save_ca_files(
    cert_root: str,
    cert_sub: str,
    ca_key_pem: bytes,
    ca_cert_pem: bytes,
) -> None:
    """保存 CA 证书文件到磁盘"""
    ca_dir = get_ca_dir(cert_root, cert_sub)
    ca_dir.mkdir(parents=True, exist_ok=True)

    key_path = ca_dir / 'ca.key'
    key_path.write_bytes(ca_key_pem)
    os.chmod(key_path, 0o600)

    cert_path = ca_dir / 'ca.crt'
    cert_path.write_bytes(ca_cert_pem)
    os.chmod(cert_path, 0o600)

    logger.info("CA 证书文件已保存: %s", ca_dir)


def delete_cert_files(cert_root: str, cert_sub: str) -> bool:
    """删除证书文件目录"""
    cert_dir = get_cert_dir(cert_root, cert_sub)
    if cert_dir.exists():
        shutil.rmtree(cert_dir)
        parent_dir = cert_dir.parent
        try:
            parent_dir.rmdir()
        except OSError:
            pass
        logger.info("证书文件已删除: %s", cert_dir)
        return True
    return False


def delete_ca_files(cert_root: str, cert_sub: str) -> bool:
    """删除 CA 证书文件目录"""
    ca_dir = get_ca_dir(cert_root, cert_sub)
    if ca_dir.exists():
        shutil.rmtree(ca_dir)
        parent_dir = ca_dir.parent
        try:
            parent_dir.rmdir()
        except OSError:
            pass
        logger.info("CA 证书文件已删除: %s", ca_dir)
        return True
    return False
