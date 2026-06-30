"""行为验证码系统模块。

提供：

* 提供者基类与数据结构（:mod:`app.captcha.base`）；
* 提供者注册表（:mod:`app.captcha.registry`）；
* Redis 状态存储（:mod:`app.captcha.storage`）；
* SVG 图片生成（:mod:`app.captcha.svg`）；
* 词库（:mod:`app.captcha.wordpool`）；
* 内置 7 种验证码类型（:mod:`app.captcha.types`）；
* FastAPI 路由（:mod:`app.captcha.router`）；
* 验证依赖（:mod:`app.captcha.dependencies`）。

应用启动时调用 :func:`register_builtins` 注册内置类型，第三方插件在
``on_load`` 中调用 :func:`app.captcha.registry.register` 注入自定义类型。

支持的内置类型：

* ``slider`` — 简单滑块（drag-to-end，纯行为校验）
* ``slider_image`` — 滑块拼图（jigsaw puzzle）
* ``rotate`` — 旋转还原
* ``text_click`` — 文字点选（按显示顺序）
* ``sequence_click`` — 语序点选（成语/诗句顺序）
* ``region_click`` — 区域点选（点击所有目标形状）
* ``reasoning_click`` — 推理点选（按属性推理）
"""
from __future__ import annotations

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.builtin import register_builtins
from app.captcha.registry import captcha_registry, register

__all__ = [
    "CaptchaChallenge",
    "CaptchaProvider",
    "VerifyResult",
    "captcha_registry",
    "register",
    "register_builtins",
]
