"""验证码提供者注册表。

维护 ``type_id -> CaptchaProvider`` 映射，供路由层按类型生成题目，
以及按题目类型分发校验。

内置验证码在应用启动时由 :func:`app.captcha.builtin.register_builtins`
注册；第三方插件可在 ``on_load`` 中调用 :func:`register` 注入自定义类型。
"""
from __future__ import annotations

import logging

from app.captcha.base import CaptchaProvider

logger = logging.getLogger(__name__)


class CaptchaRegistry:
    """验证码注册表（单例）。

    用法::

        from app.captcha.registry import captcha_registry

        captcha_registry.register(MyProvider())
        provider = captcha_registry.get("slider_image")
    """

    def __init__(self) -> None:
        self._providers: dict[str, CaptchaProvider] = {}

    def register(self, provider: CaptchaProvider) -> None:
        """注册提供者。重复 ``type_id`` 覆盖并记录警告。"""
        if not provider.type_id:
            raise ValueError("验证码提供者缺少 type_id")
        if provider.type_id in self._providers:
            logger.warning(
                "验证码类型 %s 已注册（%s），将被覆盖为 %s",
                provider.type_id,
                type(self._providers[provider.type_id]).__name__,
                type(provider).__name__,
            )
        self._providers[provider.type_id] = provider
        logger.info("已注册验证码: %s (%s)", provider.type_id, provider.name)

    def get(self, type_id: str) -> CaptchaProvider | None:
        """按 ``type_id`` 获取提供者。"""
        return self._providers.get(type_id)

    def list_all(self) -> list[CaptchaProvider]:
        return list(self._providers.values())

    def list_metadata(self) -> list[dict]:
        return [p.metadata for p in self._providers.values()]

    def random_type_id(self) -> str | None:
        """随机返回一个已注册类型 ID（用于默认场景）。"""
        if not self._providers:
            return None
        import secrets

        return secrets.choice(list(self._providers.keys()))

    def clear(self) -> None:
        self._providers.clear()


#: 模块级单例
captcha_registry = CaptchaRegistry()


def register(provider: CaptchaProvider) -> None:
    """便捷函数：注册到全局注册表。"""
    captcha_registry.register(provider)
