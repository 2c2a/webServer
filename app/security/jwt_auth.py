"""Ed25519 签名的 JWT Access Token。

- 算法：EdDSA（Ed25519），非对称签名，私钥签发、公钥验签
- 有效期：5 分钟（access_token_ttl_seconds）
- 存放：前端内存（不落 Cookie/LocalStorage，防 XSS 窃取）
- 撤销：ban_version 机制，Payload 携带版本号，封禁时递增数据库版本
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_ALG = "EdDSA"


def _load_private_key() -> Ed25519PrivateKey:
    pem = settings.ed25519_private_key_pem
    if pem:
        return serialization.load_pem_private_key(pem.encode(), password=None)  # type: ignore[return-value]
    if settings.debug:
        # 开发模式：从 secret_key 派生确定性 Ed25519 密钥（仅用于本地）
        import hashlib

        seed = hashlib.sha256(b"ed25519:" + settings.secret_key.encode()).digest()[:32]
        return Ed25519PrivateKey.from_private_bytes(seed)
    raise ValueError("ed25519_private_key_pem 必须在生产环境显式配置")


def _load_public_key() -> Ed25519PublicKey:
    pem = settings.ed25519_public_key_pem
    if pem:
        return serialization.load_pem_public_key(pem.encode())  # type: ignore[return-value]
    # 未配置公钥时从私钥派生（开发模式）
    return _load_private_key().public_key()


_private_key = _load_private_key()
_public_key = _load_public_key()

# PyJWT 接受 cryptography 的 Ed25519 私钥/公钥对象
_SIGN_KEY = _private_key
_VERIFY_KEY = _public_key


def issue_access_token(
    *,
    user_id: int,
    username: str,
    ban_version: int,
    site_group_id: int | None = None,
    is_superuser: bool = False,
    is_staff: bool = False,
    extra: dict[str, Any] | None = None,
) -> str:
    """签发 Access Token JWT。

    Payload 包含：
    - sub: 用户 ID
    - username: 用户名
    - bv: ban_version（封禁版本号，用于无状态秒级撤销）
    - sg: 站点组 ID
    - su/is_staff: 角色标记
    - exp/iat/jti: 标准声明
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "bv": ban_version,
        "sg": site_group_id,
        "su": is_superuser,
        "is_staff": is_staff,
        "iat": now,
        "exp": now + settings.access_token_ttl_seconds,
        "jti": uuid.uuid4().hex,
    }
    if extra:
        payload["extra"] = extra
    return jwt.encode(payload, _SIGN_KEY, algorithm=_ALG)


def decode_access_token(token: str) -> dict[str, Any]:
    """验签并解码 Access Token。过期或签名无效抛 jwt 异常。"""
    return jwt.decode(token, _VERIFY_KEY, algorithms=[_ALG])


# 密码重置令牌有效期（秒）：10 分钟
PASSWORD_RESET_TOKEN_TTL = 600


def issue_password_reset_token(*, user_id: int, ban_version: int) -> str:
    """签发密码重置令牌（Ed25519 签名，10 分钟有效）。

    与 Access Token 区分：Payload 携带 ``purpose="password_reset"``，
    且不含登录态角色信息；仅用于「忘记密码」自助重置流程的二次校验。
    ``bv`` 携带签发时的 ban_version，重置时再次比对，封禁期间令牌自动失效。
    """
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "purpose": "password_reset",
        "bv": ban_version,
        "iat": now,
        "exp": now + PASSWORD_RESET_TOKEN_TTL,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, _SIGN_KEY, algorithm=_ALG)


def decode_password_reset_token(token: str) -> dict[str, Any] | None:
    """验签并解码密码重置令牌。无效、过期或用途不符返回 None。"""
    if not token:
        return None
    try:
        payload = jwt.decode(token, _VERIFY_KEY, algorithms=[_ALG])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "password_reset":
        return None
    return payload


def get_public_key_pem() -> str:
    """导出公钥 PEM（供前端/外部验签）。"""
    return _public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
