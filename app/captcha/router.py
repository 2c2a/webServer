"""验证码 FastAPI 路由。

提供：

* ``GET /captcha/types`` — 列出所有可用类型
* ``GET /captcha/generate`` — 生成一道题目（默认随机类型）
* ``POST /captcha/verify`` — 校验用户答案（HMAC-SHA256 签名）
* ``GET /captcha/widget`` — 渲染嵌入式 widget 片段（HTMX）
* ``POST /captcha/verify-fragment`` — 返回验证结果片段（HTMX）

所有路由不依赖用户登录状态，但依赖租户上下文（用于站点隔离的频率限制）。
"""
from __future__ import annotations

import json
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from pydantic import BaseModel, Field

from app.cache.fragments import fragment_response
from app.captcha.registry import captcha_registry
from app.captcha.scene_config import get_captcha_scene_config
from app.captcha.signing import attach_sign_key, load_sign_key, verify_signature
from app.captcha.storage import (
    delete_challenge,
    load_challenge,
    save_challenge,
    update_challenge,
)
from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.logging import get_logger
from app.templates import render_template
from app.tenant.dependencies import get_client_ip, get_tenant
from app.tenant.resolver import TenantContext

log = get_logger(__name__)

router = APIRouter(prefix="/captcha", tags=["captcha"])


# ──────────────────────────────────────────────────────────────
# Schema
# ──────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    type: str | None = Field(None, description="指定类型，留空则随机")


class VerifyRequest(BaseModel):
    captcha_id: str
    answer: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────
# JSON API
# ──────────────────────────────────────────────────────────────


@router.get("/types")
async def list_types():
    """列出所有已注册验证码类型。"""
    return {"types": captcha_registry.list_metadata()}


@router.get("/config/{scene}")
async def get_scene_config(scene: str):
    """读取某场景的验证码配置，供前端决定是否启用 + 使用哪种类型。

    返回：``{"enabled": bool, "type": str}``，``type`` 为空表示随机。
    """
    if scene not in ("login", "register", "email"):
        raise AppError("未知场景", "captcha_bad_scene", 400)
    cfg = await get_captcha_scene_config(scene)
    return {"enabled": cfg.enabled, "type": cfg.type}


@router.post("/generate")
async def generate(body: GenerateRequest = None):
    """生成一道验证码题目。"""
    type_id = (body.type if body else None) or captcha_registry.random_type_id()
    if type_id is None:
        raise AppError("未注册任何验证码类型", "captcha_empty")
    provider = captcha_registry.get(type_id)
    if provider is None:
        raise NotFoundError(f"未知验证码类型: {type_id}")

    captcha_id = secrets.token_urlsafe(16)
    challenge = await provider.generate(captcha_id)
    # 为每个 captcha 附加一次性 HMAC 签名密钥
    attach_sign_key(challenge.meta, challenge.state)
    await save_challenge(challenge)
    log.info("captcha_generated", captcha_id=captcha_id, type=type_id)
    return challenge.to_public_dict()


@router.post("/verify")
async def verify(request: Request):
    """校验用户答案（带 HMAC-SHA256 签名校验）。

    请求头要求：
    * ``X-Captcha-Ts``: 客户端时间戳（秒）
    * ``X-Captcha-Sign``: HMAC-SHA256(sign_key, body_json + "|" + ts) hex

    签名密钥在 ``generate`` 响应的 ``meta.sign_key`` 字段（base64url）。
    """
    # 读取原始 body bytes（用于签名校验，必须与前端 JSON.stringify 完全一致）
    body_bytes = await request.body()
    body_text = body_bytes.decode("utf-8")

    # 解析 JSON
    try:
        body_data = json.loads(body_text) if body_text else {}
    except json.JSONDecodeError:
        raise AppError("请求体格式错误", "captcha_bad_request", 400)

    captcha_id = body_data.get("captcha_id")
    answer = body_data.get("answer") or {}
    if not captcha_id or not isinstance(captcha_id, str):
        raise AppError("缺少 captcha_id", "captcha_bad_request", 400)

    challenge = await load_challenge(captcha_id)
    if challenge is None:
        raise AppError("验证码已过期或不存在", "captcha_expired", 410)
    if challenge.verified:
        raise AppError("验证码已使用，请重新获取", "captcha_used", 410)
    if challenge.expires_at < time.time():
        await delete_challenge(captcha_id)
        raise AppError("验证码已过期", "captcha_expired", 410)

    # ── HMAC-SHA256 签名校验 ──
    sign_key = load_sign_key(challenge.state)
    ts_header = request.headers.get("X-Captcha-Ts", "")
    sign_header = request.headers.get("X-Captcha-Sign", "")

    # 开发模式：签名缺失时跳过校验（便于 curl 调试）
    skip_sign = settings.debug and not ts_header and not sign_header

    if skip_sign:
        sign_ok, sign_err = True, ""
        ts = int(time.time())
    else:
        try:
            ts = int(ts_header)
        except (ValueError, TypeError):
            raise AppError("缺少签名时间戳", "captcha_sign_missing", 400)
        last_ts = int(challenge.state.get("last_ts", 0))
        sign_ok, sign_err = verify_signature(
            sign_key, body_text, ts, sign_header,
            last_ts=last_ts,
        )

    if not sign_ok:
        log.warning(
            "captcha_sign_failed",
            captcha_id=captcha_id,
            error=sign_err,
        )
        # 签名失败不消耗尝试次数（直接拒绝，可能是攻击者）
        raise AppError(f"签名校验失败：{sign_err}", "captcha_sign_invalid", 400)

    # 签名通过，更新 last_ts（防重放）
    challenge.state["last_ts"] = ts

    provider = captcha_registry.get(challenge.type)
    if provider is None:
        await delete_challenge(captcha_id)
        raise AppError("验证码类型未注册", "captcha_unknown_type", 500)

    # 递增尝试次数
    challenge.attempts += 1
    if challenge.attempts > challenge.max_attempts:
        await delete_challenge(captcha_id)
        raise AppError("尝试次数已用尽，请重新获取", "captcha_max_attempts", 410)

    result = await provider.verify(challenge, answer)
    if result.success:
        challenge.verified = True
        await update_challenge(challenge)
        log.info("captcha_verified", captcha_id=captcha_id, type=challenge.type)
        return {
            "success": True,
            "message": result.message,
            "captcha_id": captcha_id,
        }
    # 失败：如果还有尝试次数，更新；否则删除
    if challenge.attempts >= challenge.max_attempts:
        await delete_challenge(captcha_id)
    else:
        await update_challenge(challenge)
    log.info(
        "captcha_verify_failed",
        captcha_id=captcha_id,
        type=challenge.type,
        message=result.message,
    )
    return {
        "success": False,
        "message": result.message,
        "need_refresh": result.need_refresh,
        "remaining_attempts": result.remaining_attempts,
    }


# ──────────────────────────────────────────────────────────────
# HTMX 片段路由
# ──────────────────────────────────────────────────────────────


@router.get("/widget")
async def widget_fragment(
    request: Request,
    type: str | None = None,
    target: str = "captcha-container",
):
    """渲染嵌入式 widget 片段。

    前端用法::

        <div id="captcha-container"
             hx-get="/captcha/widget?target=captcha-container"
             hx-trigger="load"
             hx-target="this"></div>
    """
    type_id = type or captcha_registry.random_type_id()
    if type_id is None:
        raise AppError("未注册任何验证码类型", "captcha_empty")
    provider = captcha_registry.get(type_id)
    if provider is None:
        raise NotFoundError(f"未知验证码类型: {type_id}")

    captcha_id = secrets.token_urlsafe(16)
    challenge = await provider.generate(captcha_id)
    attach_sign_key(challenge.meta, challenge.state)
    await save_challenge(challenge)

    html = await render_template(
        "captcha/widget.html",
        challenge=challenge,
        target=target,
        request=request,
    )
    return fragment_response(html, request=request)


@router.post("/verify-fragment")
async def verify_fragment(
    request: Request,
    captcha_id: str = Form(...),
    payload: str = Form(""),
    target: str = Form("captcha-container"),
):
    """HTMX 校验路由，返回 widget 片段（带成功 / 失败状态）。

    ``payload`` 为 JSON 字符串，包含 x / angle / points 等答案字段。
    """
    import json

    try:
        answer = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        answer = {}

    challenge = await load_challenge(captcha_id)
    if challenge is None:
        html = await render_template(
            "captcha/widget.html",
            challenge=None,
            target=target,
            error="验证码已过期，请重新获取",
            request=request,
        )
        return fragment_response(html, request=request)

    if challenge.verified:
        html = await render_template(
            "captcha/widget.html",
            challenge=challenge,
            target=target,
            success=True,
            message="已验证通过",
            request=request,
        )
        return fragment_response(html, request=request)

    if challenge.expires_at < time.time():
        await delete_challenge(captcha_id)
        html = await render_template(
            "captcha/widget.html",
            challenge=None,
            target=target,
            error="验证码已过期，请重新获取",
            request=request,
        )
        return fragment_response(html, request=request)

    provider = captcha_registry.get(challenge.type)
    if provider is None:
        await delete_challenge(captcha_id)
        html = await render_template(
            "captcha/widget.html",
            challenge=None,
            target=target,
            error="验证码类型未注册",
            request=request,
        )
        return fragment_response(html, request=request)

    challenge.attempts += 1
    if challenge.attempts > challenge.max_attempts:
        await delete_challenge(captcha_id)
        html = await render_template(
            "captcha/widget.html",
            challenge=None,
            target=target,
            error="尝试次数已用尽，请重新获取",
            request=request,
        )
        return fragment_response(html, request=request)

    result = await provider.verify(challenge, answer)
    if result.success:
        challenge.verified = True
        await update_challenge(challenge)
        html = await render_template(
            "captcha/widget.html",
            challenge=challenge,
            target=target,
            success=True,
            message=result.message,
            request=request,
        )
        return fragment_response(html, request=request)

    # 失败：根据 need_refresh 决定是否换题
    if result.need_refresh or challenge.attempts >= challenge.max_attempts:
        await delete_challenge(captcha_id)
        # 生成新题
        new_type = captcha_registry.random_type_id() or challenge.type
        new_provider = captcha_registry.get(new_type)
        if new_provider is not None:
            new_id = secrets.token_urlsafe(16)
            new_challenge = await new_provider.generate(new_id)
            attach_sign_key(new_challenge.meta, new_challenge.state)
            await save_challenge(new_challenge)
            html = await render_template(
                "captcha/widget.html",
                challenge=new_challenge,
                target=target,
                error=result.message,
                request=request,
            )
            return fragment_response(html, request=request)
        html = await render_template(
            "captcha/widget.html",
            challenge=None,
            target=target,
            error=result.message,
            request=request,
        )
        return fragment_response(html, request=request)

    # 失败但不换题
    await update_challenge(challenge)
    html = await render_template(
        "captcha/widget.html",
        challenge=challenge,
        target=target,
        error=result.message,
        request=request,
    )
    return fragment_response(html, request=request)


@router.get("/health")
async def health():
    """验证码系统健康检查。"""
    return {
        "registered_types": [p.type_id for p in captcha_registry.list_all()],
        "redis_enabled": settings.redis_enabled,
    }
