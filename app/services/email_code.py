"""邮箱验证码服务（注册场景）。

存储与频率限制：
- 验证码与状态写入 Redis，键 ``email_code:{email_lower}``，TTL 由配置决定
- 同一邮箱两次发送间隔 ``email_code_resend_interval_seconds`` 秒
- 验证时累加尝试次数，超过 ``email_code_max_attempts`` 自动失效
- 验证成功后立即删除（一次性消费）

Redis 不可用时自动降级到进程内存（开发场景），与 captcha.storage 行为一致。

注意：验证码以明文 6 位数字存储（10 分钟 TTL + 最多 5 次尝试），不做单向哈希。
原因：服务端生成 + 服务端校验 + 一次性消费 + 严格 TTL，无离线撞库窗口；
若需要更高安全等级可改为 Argon2 哈希存储，但会增加实现复杂度且收益有限。
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

log = get_logger(__name__)

KEY_PREFIX = "email_code"

#: 进程内后备存储（Redis 不可用时使用）
_memory_store: dict[str, dict[str, Any]] = {}

#: Redis 不可用标记
_use_memory_fallback: bool = False


def _should_use_memory() -> bool:
    if _use_memory_fallback:
        return True
    if not settings.redis_enabled:
        return True
    return False


def _key(email: str) -> str:
    return f"{KEY_PREFIX}:{email.lower().strip()}"


def _generate_code() -> str:
    """生成 6 位数字验证码（首位允许 0）。"""
    return f"{secrets.randbelow(1_000_000):06d}"


def _serialize(code: str, attempts: int) -> str:
    return json.dumps(
        {"code": code, "attempts": attempts, "ts": time.time()},
        ensure_ascii=False,
    )


def _deserialize(raw: str) -> dict[str, Any]:
    return json.loads(raw)


async def issue_code(email: str) -> tuple[str, int] | None:
    """为邮箱生成验证码并存储。

    Returns:
        (code, ttl_seconds) - 成功时返回验证码与剩余有效期
        None - 距上次发送不足 ``resend_interval`` 秒，请稍后再试
    """
    email_l = email.lower().strip()
    ttl = settings.email_code_ttl_seconds
    resend_interval = settings.email_code_resend_interval_seconds

    # 频率限制：检查距上次发送的时间
    now = time.time()
    if _should_use_memory():
        entry = _memory_store.get(_key(email_l))
        if entry and now - entry["ts"] < resend_interval:
            return None
        code = _generate_code()
        _memory_store[_key(email_l)] = {
            "code": code,
            "attempts": 0,
            "ts": now,
            "expires_at": now + ttl,
        }
        return code, ttl

    try:
        redis = await get_redis()
        existing = await redis.get(_key(email_l))
        if existing:
            data = _deserialize(existing)
            if now - data.get("ts", 0) < resend_interval:
                return None
        code = _generate_code()
        await redis.set(_key(email_l), _serialize(code, 0), ex=ttl)
        return code, ttl
    except Exception as e:  # noqa: BLE001
        log.warning("email_code_redis_issue_failed", error=str(e))
        global _use_memory_fallback
        _use_memory_fallback = True
        # 降级到内存
        return await issue_code(email)


async def verify_code(email: str, code: str) -> bool:
    """校验验证码：成功后立即删除（一次性消费）。

    失败时累加尝试次数，超过上限自动失效。
    """
    email_l = email.lower().strip()
    key = _key(email_l)
    code = code.strip()

    if _should_use_memory():
        entry = _memory_store.get(key)
        if entry is None:
            return False
        if entry["expires_at"] < time.time():
            _memory_store.pop(key, None)
            return False
        if entry["code"] != code:
            return False
        _memory_store.pop(key, None)
        return True

    try:
        redis = await get_redis()
        raw = await redis.get(key)
        if raw is None:
            return False
        data = _deserialize(raw)
        if data.get("code") != code:
            # 累加尝试次数
            attempts = data.get("attempts", 0) + 1
            if attempts >= settings.email_code_max_attempts:
                await redis.delete(key)
            else:
                ttl = await redis.ttl(key)
                if ttl > 0:
                    await redis.set(key, _serialize(data["code"], attempts), ex=ttl)
            return False
        # 成功：删除
        await redis.delete(key)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("email_code_redis_verify_failed", error=str(e))
        global _use_memory_fallback
        _use_memory_fallback = True
        return await verify_code(email, code)


async def peek_ttl(email: str) -> int:
    """返回邮箱验证码剩余 TTL（秒），用于响应中提示前端倒计时。

    不存在时返回 0。
    """
    email_l = email.lower().strip()
    if _should_use_memory():
        entry = _memory_store.get(_key(email_l))
        if entry is None:
            return 0
        remaining = int(entry["expires_at"] - time.time())
        return max(0, remaining)
    try:
        redis = await get_redis()
        return await redis.ttl(_key(email_l))
    except Exception as e:  # noqa: BLE001
        log.warning("email_code_redis_peek_failed", error=str(e))
        global _use_memory_fallback
        _use_memory_fallback = True
        return await peek_ttl(email)


@dataclass
class IssueResult:
    """发送验证码的结果。"""
    success: bool
    code: str | None = None
    ttl: int = 0
    resend_in: int = 0  # 距下次可发送剩余秒数（被频率限制时 > 0）


async def try_issue(email: str) -> IssueResult:
    """带频率限制的发送：成功返回 code+ttl，被限制时返回 resend_in。"""
    result = await issue_code(email)
    if result is None:
        # 频率限制中
        ttl = await peek_ttl(email)
        return IssueResult(
            success=False,
            ttl=ttl,
            resend_in=settings.email_code_resend_interval_seconds,
        )
    code, ttl = result
    return IssueResult(success=True, code=code, ttl=ttl)
