"""内置验证码提供者注册。

应用启动时（``main.lifespan``）调用 :func:`register_builtins` 注册全部
内置类型，第三方插件可在 ``on_load`` 中调用
:func:`app.captcha.registry.register` 注入自定义类型。
"""
from __future__ import annotations

from app.captcha.registry import captcha_registry
from app.captcha.types import (
    ReasoningClickProvider,
    RegionClickProvider,
    RotateProvider,
    SequenceClickProvider,
    SliderImageProvider,
    SliderProvider,
    TextClickProvider,
)


def register_builtins() -> None:
    """注册全部内置验证码类型。"""
    providers = [
        SliderProvider(),
        SliderImageProvider(),
        RotateProvider(),
        TextClickProvider(),
        SequenceClickProvider(),
        RegionClickProvider(),
        ReasoningClickProvider(),
    ]
    for p in providers:
        captcha_registry.register(p)
