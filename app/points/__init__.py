"""积分系统模块。

提供：

* 检测器基类与上下文（:mod:`app.points.detectors`）；
* 检测器注册表（:mod:`app.points.registry`）；
* 内置检测器（:mod:`app.points.builtin`）；
* 积分服务（:mod:`app.points.service`）；
* Pydantic Schema（:mod:`app.points.schemas`）。

应用启动时调用 :func:`app.points.builtin.register_builtins` 注册内置
检测方式，第三方插件在 ``on_load`` 中调用
:func:`app.points.registry.register` 注入自定义检测方式。
"""
from __future__ import annotations

from app.points.builtin import register_builtins
from app.points.detectors import DetectorContext, PointTaskDetector
from app.points.registry import point_detector_registry, register

__all__ = [
    "DetectorContext",
    "PointTaskDetector",
    "point_detector_registry",
    "register",
    "register_builtins",
]
