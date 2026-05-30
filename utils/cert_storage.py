import os
import secrets
import shutil
from pathlib import Path
from django.conf import settings


def get_cert_base_dir():
    return Path(settings.MEDIA_ROOT) / 'certificates'


def get_cert_dir(cert_root: str, cert_sub: str):
    return get_cert_base_dir() / cert_root / cert_sub


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
