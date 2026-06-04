import os
import re
import secrets
import shutil
from pathlib import Path
from django.conf import settings


def _sanitizePathComponent(value: str) -> str:
    """过滤非字母数字字符，防止路径穿越"""
    return re.sub(r'[^a-zA-Z0-9]', '', value)


def get_cert_base_dir():
    return Path(settings.MEDIA_ROOT) / 'certificates'


def get_cert_dir(cert_root: str, cert_sub: str):
    return (
        get_cert_base_dir()
        / _sanitizePathComponent(cert_root)
        / _sanitizePathComponent(cert_sub)
    )


def generate_cert_paths():
    cert_root = secrets.token_hex(1)
    cert_sub = secrets.token_hex(1)
    return cert_root, cert_sub


def save_cert_files(
    cert_root: str,
    cert_sub: str,
    ca_cert_pem: bytes,
    client_cert_pem: bytes,
    server_pfx_bytes: bytes,
    client_key_pem: bytes | None = None,
):
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

    return cert_dir


def delete_cert_files(cert_root: str, cert_sub: str):
    cert_dir = get_cert_dir(cert_root, cert_sub)
    if cert_dir.exists():
        shutil.rmtree(cert_dir)
        parent_dir = cert_dir.parent
        try:
            parent_dir.rmdir()
        except OSError:
            # Best-effort cleanup: parent may be non-empty or changed concurrently.
            pass
        return True
    return False


def get_cert_file_paths(cert_root: str, cert_sub: str):
    cert_dir = get_cert_dir(cert_root, cert_sub)
    return {
        'ca_cert': cert_dir / 'ca.crt',
        'client_cert': cert_dir / 'client.crt',
        'client_key': cert_dir / 'client.key',
        'server_pfx': cert_dir / 'server.pfx',
    }


def get_ca_base_dir():
    return Path(settings.MEDIA_ROOT) / 'certificates' / 'ca'


def get_ca_dir(cert_root: str, cert_sub: str):
    return (
        get_ca_base_dir()
        / _sanitizePathComponent(cert_root)
        / _sanitizePathComponent(cert_sub)
    )


def generate_ca_paths():
    cert_root = secrets.token_hex(1)
    cert_sub = secrets.token_hex(1)
    return cert_root, cert_sub


def save_ca_files(cert_root: str, cert_sub: str, ca_key_pem: bytes, ca_cert_pem: bytes):
    ca_dir = get_ca_dir(cert_root, cert_sub)
    ca_dir.mkdir(parents=True, exist_ok=True)

    key_path = ca_dir / 'ca.key'
    key_path.write_bytes(ca_key_pem)
    os.chmod(key_path, 0o600)

    cert_path = ca_dir / 'ca.crt'
    cert_path.write_bytes(ca_cert_pem)
    os.chmod(cert_path, 0o600)

    return ca_dir


def get_ca_file_paths(cert_root: str, cert_sub: str):
    ca_dir = get_ca_dir(cert_root, cert_sub)
    return {
        'key': ca_dir / 'ca.key',
        'cert': ca_dir / 'ca.crt',
    }


def delete_ca_files(cert_root: str, cert_sub: str):
    ca_dir = get_ca_dir(cert_root, cert_sub)
    if ca_dir.exists():
        shutil.rmtree(ca_dir)
        parent_dir = ca_dir.parent
        try:
            parent_dir.rmdir()
        except OSError:
            # Best-effort cleanup: parent may be non-empty or changed concurrently.
            pass
        return True
    return False
