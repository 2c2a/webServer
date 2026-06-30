"""AES-GCM 加密的 Refresh Token（HttpOnly Cookie）。

- 算法：AES-256-GCM（主密钥派生）
- 有效期：7 天（refresh_token_ttl_days）
- 存放：HttpOnly + Secure + SameSite=Strict Cookie，防 XSS 读取
- 载荷：用户 ID + ban_version + 站点组 + 过期时间 + 随机 jti
- 轮换：每次刷新签发新 Refresh Token（滑动窗口）
"""
from __future__ import annotations

import json
import time
import uuid

from app.core.config import settings
from app.security.crypto import aes_gcm_decrypt, aes_gcm_encrypt, derive_field_key

# Refresh Token 专用派生密钥（与字段级加密隔离）
_RT_KEY = derive_field_key("refresh_token")


def issue_refresh_token(
    *,
    user_id: int,
    ban_version: int,
    site_group_id: int | None = None,
) -> str:
    """签发加密 Refresh Token。"""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "bv": ban_version,
        "sg": site_group_id,
        "iat": now,
        "exp": now + settings.refresh_token_ttl_days * 86400,
        "jti": uuid.uuid4().hex,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return aes_gcm_encrypt(raw, _RT_KEY)


def decode_refresh_token(token: str) -> dict | None:
    """解密并校验 Refresh Token。无效或过期返回 None。"""
    if not token:
        return None
    try:
        raw = aes_gcm_decrypt(token, _RT_KEY)
        payload = json.loads(raw)
    except Exception:
        return None
    if int(time.time()) > payload.get("exp", 0):
        return None
    return payload


def set_refresh_cookie(response, token: str) -> None:
    """将 Refresh Token 写入 HttpOnly Cookie（path=/，兼容旧 path=/auth）。"""
    # 清理旧路径 Cookie，避免同名不同路径导致请求时携带过期令牌
    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path="/auth",
    )
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=token,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.is_prod,
        samesite="strict",
        path="/",
    )


def clear_refresh_cookie(response) -> None:
    """清除 Refresh Token Cookie（同时清除新旧路径）。"""
    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path="/",
    )
    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        path="/auth",
    )
