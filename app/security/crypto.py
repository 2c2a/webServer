"""底层加密原语：BLAKE2b / Argon2id / HKDF-SHA256 / AES-256-GCM。

所有密钥派生与加解密在此集中，供 password / field_cipher / jwt_auth / cache 复用。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

from argon2 import Type, low_level
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings


# ──────────────────────────────────────────────────────────────
# 密钥加载
# ──────────────────────────────────────────────────────────────

def _load_master_key() -> bytes:
    """加载 AES-GCM 主密钥（32 字节）。

    生产环境必须显式配置 crypto_master_key_b64（base64 编码的 32 字节）。
    演示/开发模式自动生成。
    """
    raw = settings.crypto_master_key_b64
    if raw:
        key = base64.b64decode(raw)
        if len(key) != 32:
            raise ValueError("crypto_master_key_b64 必须为 32 字节（base64 编码）")
        return key
    if settings.debug or settings.demo:
        # 开发模式：从 secret_key 派生稳定主密钥
        return hashlib.sha256(settings.secret_key.encode()).digest()
    raise ValueError("crypto_master_key_b64 必须在生产环境显式配置")


_MASTER_KEY = _load_master_key()


def master_key() -> bytes:
    return _MASTER_KEY


# ──────────────────────────────────────────────────────────────
# keyed-BLAKE2b（缓存键 / ETag / 防篡改）
# ──────────────────────────────────────────────────────────────

def _cache_key_material() -> bytes:
    raw = settings.cache_signing_key
    if raw:
        return raw.encode()
    if settings.debug or settings.demo:
        return hashlib.sha256(b"cache-key:" + settings.secret_key.encode()).digest()
    raise ValueError("cache_signing_key 必须在生产环境显式配置")


_CACHE_KEY = _cache_key_material()


def keyed_blake2b(data: str | bytes, *, context: str = "") -> str:
    """keyed-BLAKE2b 带密钥哈希，输出 hex。

    用于生成边缘缓存键与 HTMX ETag，兼顾极速与防脏数据污染。
    context 作为域分隔前缀，防止不同用途的哈希碰撞。
    """
    if isinstance(data, str):
        data = data.encode("utf-8")
    payload = context.encode() + b"|" + data
    h = hashlib.blake2b(payload, key=_CACHE_KEY, digest_size=32)
    return h.hexdigest()


def keyed_blake2b_short(data: str | bytes, *, context: str = "") -> str:
    """短哈希（16 字节），用于 ETag 等场景。"""
    if isinstance(data, str):
        data = data.encode("utf-8")
    payload = context.encode() + b"|" + data
    h = hashlib.blake2b(payload, key=_CACHE_KEY, digest_size=16)
    return h.hexdigest()


# ──────────────────────────────────────────────────────────────
# HKDF-SHA256（按字段名派生子密钥）
# ──────────────────────────────────────────────────────────────

def derive_field_key(field_name: str, *, info: bytes = b"") -> bytes:
    """HKDF-SHA256 按字段名派生 32 字节子密钥。

    实现字段级密钥隔离：每个敏感字段（如 password、smtp_password）使用
    独立派生子密钥，单字段密钥泄露不影响其他字段，且无法篡改字段名。
    """
    salt = hashlib.sha256(b"field-salt").digest()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=field_name.encode("utf-8") + b"\x00" + info,
    )
    return hkdf.derive(_MASTER_KEY)


# ──────────────────────────────────────────────────────────────
# AES-256-GCM（字段级加密 + Refresh Token 加密）
# ──────────────────────────────────────────────────────────────

def aes_gcm_encrypt(plaintext: str | bytes, key: bytes) -> str:
    """AES-256-GCM 加密，返回 base64(nonce || ciphertext || tag)。

    GCM 自带完整性校验（防篡改），nonce 每次随机 12 字节。
    """
    if isinstance(plaintext, str):
        plaintext = plaintext.encode("utf-8")
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def aes_gcm_decrypt(token: str, key: bytes) -> bytes:
    """AES-256-GCM 解密，验证失败抛异常。"""
    raw = base64.urlsafe_b64decode(token.encode("ascii"))
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, associated_data=None)


def aes_gcm_decrypt_str(token: str, key: bytes) -> str:
    return aes_gcm_decrypt(token, key).decode("utf-8")


# ──────────────────────────────────────────────────────────────
# Argon2id（密码慢哈希）
# ──────────────────────────────────────────────────────────────

def argon2id_hash(prehashed_password: bytes) -> str:
    """Argon2id 加盐慢哈希。

    输入为前端 BLAKE2b 预哈希后的定长字节（防 DoS 截断），
    输出 PHC 字符串（含盐、参数），可直接存储。
    有效抵御 GPU 与 ASIC 爆破。
    """
    return low_level.hash_secret(
        secret=prehashed_password,
        salt=os.urandom(16),
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
        hash_len=32,
        type=Type.ID,
    ).decode("ascii")


def argon2id_verify(prehashed_password: bytes, phc_hash: str) -> bool:
    """验证 Argon2id 哈希。"""
    try:
        return low_level.verify_secret(
            secret=prehashed_password,
            hash=phc_hash.encode("ascii"),
            type=Type.ID,
        )
    except Exception:
        return False


# ──────────────────────────────────────────────────────────────
# BLAKE2b 预哈希（前端配套，后端校验）
# ──────────────────────────────────────────────────────────────

def server_side_prehash(blake2b_hex: str) -> bytes:
    """将前端传来的 BLAKE2b hex 预哈希转为 Argon2id 输入字节。

    前端对原始密码做 BLAKE2b（定长输出），防止超长密码 DoS 后端 Argon2id。
    后端在此做长度与格式校验后，转为字节交给 Argon2id。
    """
    blake2b_hex = blake2b_hex.strip().lower()
    if not blake2b_hex or not all(c in "0123456789abcdef" for c in blake2b_hex):
        raise ValueError("密码预哈希格式无效")
    # 限制长度，防止伪造超长输入
    if len(blake2b_hex) > 256:
        raise ValueError("密码预哈希过长")
    return bytes.fromhex(blake2b_hex)


# ──────────────────────────────────────────────────────────────
# 常量时间比较
# ──────────────────────────────────────────────────────────────

def constant_time_eq(a: str | bytes, b: str | bytes) -> bool:
    if isinstance(a, str):
        a = a.encode()
    if isinstance(b, str):
        b = b.encode()
    return hmac.compare_digest(a, b)
