"""验证码题目存储（Redis + 内存后备）。

* Redis 启用时：题目状态写入 Redis，TTL 自动过期
* Redis 不可用时：自动降级到进程内字典（开发 / 测试场景）

存储内容：完整 :class:`CaptchaChallenge`（含 state），前端不可见。
键：``captcha:{captcha_id}``
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.captcha.base import CaptchaChallenge
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

#: Redis 键前缀
KEY_PREFIX = "captcha"

#: 进程内后备存储（Redis 不可用时使用）
_memory_store: dict[str, dict[str, Any]] = {}

#: Redis 不可用标记（一旦失败，本次进程内降级到内存）
_use_memory_fallback: bool = False


def _should_use_memory() -> bool:
    """是否使用内存后备。"""
    if _use_memory_fallback:
        return True
    if not settings.redis_enabled:
        return True
    return False


def _key(captcha_id: str) -> str:
    return f"{KEY_PREFIX}:{captcha_id}"


def _serialize(challenge: CaptchaChallenge) -> str:
    return json.dumps(
        {
            "captcha_id": challenge.captcha_id,
            "type": challenge.type,
            "image": challenge.image,
            "background": challenge.background,
            "hint": challenge.hint,
            "width": challenge.width,
            "height": challenge.height,
            "state": challenge.state,
            "meta": challenge.meta,
            "expected_clicks": challenge.expected_clicks,
            "expires_at": challenge.expires_at,
            "max_attempts": challenge.max_attempts,
            "attempts": challenge.attempts,
            "verified": challenge.verified,
        },
        ensure_ascii=False,
    )


def _deserialize(raw: str) -> CaptchaChallenge:
    d = json.loads(raw)
    return CaptchaChallenge(
        captcha_id=d["captcha_id"],
        type=d["type"],
        image=d["image"],
        background=d.get("background"),
        hint=d.get("hint", ""),
        width=d.get("width", 300),
        height=d.get("height", 180),
        state=d.get("state", {}),
        meta=d.get("meta", {}),
        expected_clicks=d.get("expected_clicks", 0),
        expires_at=d.get("expires_at", 0.0),
        max_attempts=d.get("max_attempts", 5),
        attempts=d.get("attempts", 0),
        verified=d.get("verified", False),
    )


async def save_challenge(challenge: CaptchaChallenge, *, ttl: int | None = None) -> None:
    """保存题目到存储。``ttl`` 默认使用题目剩余有效期。"""
    if ttl is None:
        ttl = max(int(challenge.expires_at - time.time()), 30)
    data = _serialize(challenge)
    if _should_use_memory():
        _memory_store[challenge.captcha_id] = {
            "data": data,
            "expires_at": challenge.expires_at,
        }
        return
    try:
        redis = await get_redis()
        await redis.set(_key(challenge.captcha_id), data, ex=ttl)
    except Exception as e:  # noqa: BLE001
        log.warning("captcha_redis_save_failed", error=str(e))
        global _use_memory_fallback
        _use_memory_fallback = True
        _memory_store[challenge.captcha_id] = {
            "data": data,
            "expires_at": challenge.expires_at,
        }


async def load_challenge(captcha_id: str) -> CaptchaChallenge | None:
    """读取题目，过期 / 不存在返回 None。"""
    if _should_use_memory():
        entry = _memory_store.get(captcha_id)
        if entry is None:
            return None
        if entry["expires_at"] < time.time():
            _memory_store.pop(captcha_id, None)
            return None
        return _deserialize(entry["data"])
    try:
        redis = await get_redis()
        raw = await redis.get(_key(captcha_id))
        if raw is None:
            return None
        return _deserialize(raw)
    except Exception as e:  # noqa: BLE001
        log.warning("captcha_redis_load_failed", error=str(e))
        global _use_memory_fallback
        _use_memory_fallback = True
        return await load_challenge(captcha_id)


async def delete_challenge(captcha_id: str) -> None:
    """删除题目（一次性消费后调用）。"""
    if _should_use_memory():
        _memory_store.pop(captcha_id, None)
        return
    try:
        redis = await get_redis()
        await redis.delete(_key(captcha_id))
    except Exception as e:  # noqa: BLE001
        log.warning("captcha_redis_delete_failed", error=str(e))
        global _use_memory_fallback
        _use_memory_fallback = True
        _memory_store.pop(captcha_id, None)


async def update_challenge(challenge: CaptchaChallenge) -> None:
    """更新题目（例如递增尝试次数、标记已验证），保留原 TTL。"""
    await save_challenge(challenge)


async def cleanup_memory() -> int:
    """清理内存后备中已过期条目（仅内存模式有效）。"""
    now = time.time()
    expired = [k for k, v in _memory_store.items() if v["expires_at"] < now]
    for k in expired:
        _memory_store.pop(k, None)
    return len(expired)
