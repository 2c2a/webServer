"""验证码请求签名（HMAC-SHA256）。

目标：
* **防篡改**：攻击者抓包后修改请求体（如改坐标 / 角度），签名不匹配 → 拒绝
* **防重放**：时间戳必须单调递增且在 60s 窗口内，同一 captcha 的旧签名无法复用
* **提升爬虫成本**：攻击者必须实现 HMAC-SHA256 + 时间戳管理，不能用裸 fetch 重放

流程：
1. ``generate`` 时为每个 captcha 生成 32 字节随机 ``sign_key``，
   存入 ``challenge.state``（私有）与 ``challenge.meta``（base64url 下发前端）
2. 前端 ``submit`` 时：
   - ``ts = Math.floor(Date.now() / 1000)``
   - ``msg = JSON.stringify(body) + "|" + ts``
   - ``sign = HMAC-SHA256(sign_key, msg)`` → hex
   - 请求头：``X-Captcha-Ts: {ts}``、``X-Captcha-Sign: {sign}``
3. 后端 ``verify`` 校验：
   - ``abs(now - ts) <= 60``（时间窗）
   - ``ts > state.last_ts``（单调递增，防重放）
   - ``HMAC(sign_key, body_raw + "|" + ts) == sign``（常量时间比对）

注意：``sign_key`` 对前端是可见的（JS 必须能拿到才能签名），
所以签名不提供机密性，只提供**完整性 + 防重放**。
真正的反爬强度来自时间戳单调递增 + body 绑定 + 一次性 captcha。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Any

#: 时间戳容差（秒）：前端时钟与后端可能存在偏差
TS_TOLERANCE = 60


def generate_sign_key() -> bytes:
    """生成 32 字节随机签名密钥。"""
    return os.urandom(32)


def sign_key_to_public(sign_key: bytes) -> str:
    """把 sign_key 编码为 base64url 字符串，下发前端。"""
    return base64.urlsafe_b64encode(sign_key).decode("ascii").rstrip("=")


def sign_key_from_public(public: str) -> bytes:
    """从前端格式还原 sign_key。"""
    pad = "=" * (-len(public) % 4)
    return base64.urlsafe_b64decode(public + pad)


def compute_signature(sign_key: bytes, body_json: str, ts: int) -> str:
    """计算 HMAC-SHA256 签名，返回 hex。

    ``body_json`` 必须是与前端 ``JSON.stringify(body)`` 完全一致的字符串。
    """
    msg = f"{body_json}|{ts}".encode("utf-8")
    return hmac.new(sign_key, msg, hashlib.sha256).hexdigest()


def verify_signature(
    sign_key: bytes,
    body_json: str,
    ts: int,
    signature: str,
    *,
    last_ts: int = 0,
    now: float | None = None,
) -> tuple[bool, str]:
    """校验签名。

    返回 ``(ok, error_message)``。``ok=True`` 时 ``error_message`` 为空。

    校验顺序（快速失败）：
    1. 时间戳格式与时间窗
    2. 单调递增（防重放）
    3. HMAC 常量时间比对（防篡改）
    """
    if now is None:
        now = time.time()
    # 1. 时间窗
    if abs(now - ts) > TS_TOLERANCE:
        return False, "时间戳超出容许窗口"
    # 2. 单调递增（同一 captcha 后续请求的 ts 必须更大）
    if ts <= last_ts:
        return False, "时间戳无效（疑似重放）"
    # 3. HMAC 比对
    expected = compute_signature(sign_key, body_json, ts)
    if not hmac.compare_digest(expected, signature):
        return False, "签名校验失败"
    return True, ""


def attach_sign_key(meta: dict[str, Any], state: dict[str, Any]) -> bytes:
    """生成 sign_key，分别写入 meta（公开）与 state（私有）。

    返回生成的 sign_key（字节），供调用方继续使用。
    """
    sign_key = generate_sign_key()
    meta["sign_key"] = sign_key_to_public(sign_key)
    state["sign_key"] = base64.b64encode(sign_key).decode("ascii")
    state["last_ts"] = 0
    return sign_key


def load_sign_key(state: dict[str, Any]) -> bytes:
    """从 state 还原 sign_key。"""
    return base64.b64decode(state["sign_key"].encode("ascii"))
