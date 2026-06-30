"""验证码场景配置服务。

按场景（login / register / email）读取 SystemConfig 中的开关与类型，
带进程内缓存降低 DB 压力（配置变更时通过 ``invalidate_captcha_config_cache`` 失效）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import SystemConfig

#: 场景类型
Scene = Literal["login", "register", "email"]

#: 缓存有效期（秒）
_CACHE_TTL = 30

_cache: dict[str, tuple[float, "CaptchaSceneConfig"]] = {}


@dataclass
class CaptchaSceneConfig:
    """某场景的验证码配置快照。"""

    enabled: bool
    type: str  # 具体类型（如 slider_image），空字符串表示随机


def _scene_field(config: SystemConfig, scene: Scene) -> tuple[bool, str | None]:
    """根据场景返回 (enabled, type_override)。"""
    if scene == "login":
        return config.captcha_required_on_login, config.login_captcha_type
    if scene == "register":
        return config.captcha_required_on_register, config.register_captcha_type
    if scene == "email":
        return config.captcha_required_on_email, config.email_captcha_type
    return True, None


async def get_captcha_scene_config(scene: Scene) -> CaptchaSceneConfig:
    """读取某场景的验证码配置。

    优先用进程缓存，缓存失效或首次访问时查 DB。
    """
    now = time.time()
    cached = _cache.get(scene)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]

    # 从 DB 读取 SystemConfig 单例
    from app.core.db import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SystemConfig).where(SystemConfig.id == 1)
        )
        cfg = result.scalar_one_or_none()

    if cfg is None:
        # 配置未初始化，用默认值
        return CaptchaSceneConfig(enabled=True, type="")

    if not cfg.captcha_enabled:
        # 全局关闭
        result = CaptchaSceneConfig(enabled=False, type="")
    else:
        scene_enabled, scene_type = _scene_field(cfg, scene)
        if not scene_enabled:
            result = CaptchaSceneConfig(enabled=False, type="")
        else:
            # 场景类型 → 全局默认类型 → 空（随机）
            type_str = (scene_type or cfg.captcha_type or "").lower()
            result = CaptchaSceneConfig(enabled=True, type=type_str)

    _cache[scene] = (now, result)
    return result


def invalidate_captcha_config_cache() -> None:
    """清除场景配置缓存（保存配置后调用）。"""
    _cache.clear()


async def get_captcha_scene_config_with_session(
    session: AsyncSession, scene: Scene
) -> CaptchaSceneConfig:
    """在已有 session 中读取配置（用于事务内一致性读取）。"""
    result = await session.execute(
        select(SystemConfig).where(SystemConfig.id == 1)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        return CaptchaSceneConfig(enabled=True, type="")
    if not cfg.captcha_enabled:
        return CaptchaSceneConfig(enabled=False, type="")
    scene_enabled, scene_type = _scene_field(cfg, scene)
    if not scene_enabled:
        return CaptchaSceneConfig(enabled=False, type="")
    type_str = (scene_type or cfg.captcha_type or "").lower()
    return CaptchaSceneConfig(enabled=True, type=type_str)
