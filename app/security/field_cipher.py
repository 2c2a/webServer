"""字段级加密：HKDF-SHA256 按字段名派生子密钥 + AES-256-GCM。

使用方式（SQLAlchemy 模型层）：
    from app.security.field_cipher import encrypt_field, decrypt_field

    host.password_cipher = encrypt_field("password", "host.password")
    plain = decrypt_field(host.password_cipher, "host.password")

字段名约定为 "<model>.<field>"，确保全局唯一，实现字段级密钥隔离与防篡改。
"""
from __future__ import annotations

from app.security.crypto import (
    aes_gcm_decrypt_str,
    aes_gcm_encrypt,
    derive_field_key,
)

# 字段密钥缓存（进程级，避免每次 HKDF 计算）
_field_key_cache: dict[str, bytes] = {}


def _get_field_key(field_name: str) -> bytes:
    key = _field_key_cache.get(field_name)
    if key is None:
        key = derive_field_key(field_name)
        _field_key_cache[field_name] = key
    return key


def encrypt_field(plaintext: str | None, field_name: str) -> str | None:
    """加密敏感字段，返回 base64 密文。空值原样返回。"""
    if plaintext is None or plaintext == "":
        return plaintext
    key = _get_field_key(field_name)
    return aes_gcm_encrypt(plaintext, key)


def decrypt_field(ciphertext: str | None, field_name: str) -> str | None:
    """解密敏感字段。空值原样返回，解密失败抛 ValueError。"""
    if ciphertext is None or ciphertext == "":
        return ciphertext
    key = _get_field_key(field_name)
    try:
        return aes_gcm_decrypt_str(ciphertext, key)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"字段 {field_name} 解密失败") from e


def rotate_field(plaintext: str, field_name: str) -> str:
    """重新加密（密钥轮换时使用）。"""
    return encrypt_field(plaintext, field_name) or ""
