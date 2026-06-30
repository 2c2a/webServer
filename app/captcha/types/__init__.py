"""验证码类型子包导出。"""
from __future__ import annotations

from app.captcha.types.reasoning_click import ReasoningClickProvider
from app.captcha.types.region_click import RegionClickProvider
from app.captcha.types.rotate import RotateProvider
from app.captcha.types.sequence_click import SequenceClickProvider
from app.captcha.types.slider import SliderProvider
from app.captcha.types.slider_image import SliderImageProvider
from app.captcha.types.text_click import TextClickProvider

__all__ = [
    "ReasoningClickProvider",
    "RegionClickProvider",
    "RotateProvider",
    "SequenceClickProvider",
    "SliderImageProvider",
    "SliderProvider",
    "TextClickProvider",
]
