"""验证码依赖注入。

提供两种使用方式：

1. 路由内部显式校验（推荐）::

       @router.post("/login")
       async def login(body: LoginRequest, ...):
           if settings.captcha_enabled:
               await assert_captcha_solved(body.captcha_id, body.captcha)
           ...

2. FastAPI 依赖（需配合 ``CaptchaBody`` 中间件缓存请求体）::

       @router.post("/login")
       async def login(
           body: LoginRequest,
           _: CaptchaVerification = Depends(verify_captcha),
       ):
           ...

校验通过后从存储中删除题目（一次性消费）。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from app.captcha.registry import captcha_registry
from app.captcha.scene_config import Scene, get_captcha_scene_config
from app.captcha.storage import delete_challenge, load_challenge, update_challenge
from app.core.config import settings
from app.core.exceptions import AppError


@dataclass
class CaptchaVerification:
    captcha_id: str
    type: str


def _parse_answer(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


async def assert_captcha_solved(
    captcha_id: str | None,
    answer_raw: Any,
    *,
    scene: Scene = "login",
) -> CaptchaVerification:
    """显式校验：传入 captcha_id 与答案（可为 dict / JSON 字符串 / None）。

    校验通过返回 :class:`CaptchaVerification`，失败抛 :class:`AppError`。

    ``scene`` 指定当前业务场景（login / register / email），
    会从 SystemConfig 读取该场景的开关与期望类型。

    校验顺序：
    1. 全局开关（settings.captcha_enabled）
    2. 场景开关（SystemConfig.captcha_required_on_{scene}）
    3. 验证码存在性 / 过期 / 尝试次数
    4. 类型匹配（如果场景配置了具体类型）
    """
    # 全局开关（环境变量）
    if not settings.captcha_enabled:
        return CaptchaVerification(captcha_id="disabled", type="disabled")

    # 场景级开关与类型（DB 配置）
    scene_cfg = await get_captcha_scene_config(scene)
    if not scene_cfg.enabled:
        return CaptchaVerification(captcha_id="disabled", type="disabled")

    if not captcha_id:
        raise AppError("请先完成验证码", "captcha_required", 400)

    challenge = await load_challenge(captcha_id)
    if challenge is None:
        raise AppError("验证码已过期，请重新获取", "captcha_expired", 410)

    if challenge.expires_at < time.time():
        await delete_challenge(captcha_id)
        raise AppError("验证码已过期", "captcha_expired", 410)

    # 类型校验：场景配置了具体类型时，必须匹配
    if scene_cfg.type and scene_cfg.type != challenge.type:
        await delete_challenge(captcha_id)
        raise AppError(
            f"验证码类型不匹配（期望 {scene_cfg.type}）",
            "captcha_type_mismatch",
            400,
        )

    if not challenge.verified:
        # 现场校验
        provider = captcha_registry.get(challenge.type)
        if provider is None:
            await delete_challenge(captcha_id)
            raise AppError("验证码类型未注册", "captcha_unknown_type", 500)

        answer = _parse_answer(answer_raw)
        challenge.attempts += 1
        if challenge.attempts > challenge.max_attempts:
            await delete_challenge(captcha_id)
            raise AppError("尝试次数已用尽，请重新获取", "captcha_max_attempts", 410)

        result = await provider.verify(challenge, answer)
        if not result.success:
            if challenge.attempts >= challenge.max_attempts:
                await delete_challenge(captcha_id)
            else:
                await update_challenge(challenge)
            raise AppError(result.message or "验证码错误", "captcha_invalid", 400)
        # 通过：标记并保留
        challenge.verified = True
        await update_challenge(challenge)

    # 一次性消费
    await delete_challenge(captcha_id)
    return CaptchaVerification(captcha_id=captcha_id, type=challenge.type)


async def verify_captcha(request: Request) -> CaptchaVerification:
    """FastAPI 依赖：从请求体中读取 captcha_id 与 captcha 字段并校验。

    适用于请求体是 JSON 且字段名约定为 ``captcha_id`` / ``captcha`` 的场景。
    若路由同时声明了 Pydantic body 参数，请优先使用
    :func:`assert_captcha_solved` 以避免请求体二次读取。
    """
    if not settings.captcha_enabled:
        return CaptchaVerification(captcha_id="disabled", type="disabled")

    body: Any = getattr(request.state, "parsed_body", None)
    if body is None:
        try:
            body = await request.json()
        except Exception:
            body = {}
        request.state.parsed_body = body

    if isinstance(body, dict):
        captcha_id = body.get("captcha_id")
        answer_raw = body.get("captcha") or body.get("answer")
    else:
        captcha_id = getattr(body, "captcha_id", None)
        answer_raw = getattr(body, "captcha", None)

    return await assert_captcha_solved(captcha_id, answer_raw)


async def verify_captcha_optional(request: Request) -> CaptchaVerification | None:
    """可选依赖：当全局关闭或客户端未提交验证码时返回 None。"""
    if not settings.captcha_enabled:
        return None
    try:
        return await verify_captcha(request)
    except AppError:
        return None
