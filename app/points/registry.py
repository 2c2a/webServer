"""积分任务检测器注册表。

维护 ``method_id -> PointTaskDetector`` 的映射，供积分服务在运行时
按 :attr:`PointTask.detection_method` 查找对应检测器实例。

内置检测器在应用启动时由 :func:`app.points.builtin.register_builtins`
注册；第三方插件可在其 ``on_load`` 钩子中调用 :func:`register`
注入自定义检测方式。
"""
from __future__ import annotations

import logging

from app.points.detectors import PointTaskDetector

logger = logging.getLogger(__name__)


class PointDetectorRegistry:
    """积分检测器注册表（单例）。

    用法::

        from app.points.registry import point_detector_registry

        point_detector_registry.register(MyDetector())
        detector = point_detector_registry.get("daily_checkin")
    """

    def __init__(self) -> None:
        self._detectors: dict[str, PointTaskDetector] = {}

    def register(self, detector: PointTaskDetector) -> None:
        """注册检测器。重复 ``method_id`` 将覆盖并记录警告。"""
        if not detector.method_id:
            raise ValueError("检测器缺少 method_id")
        if detector.method_id in self._detectors:
            logger.warning(
                "检测方式 %s 已注册（%s），将被覆盖为 %s",
                detector.method_id,
                type(self._detectors[detector.method_id]).__name__,
                type(detector).__name__,
            )
        self._detectors[detector.method_id] = detector
        logger.info("已注册积分检测器: %s (%s)", detector.method_id, detector.name)

    def get(self, method_id: str) -> PointTaskDetector | None:
        """按 ``method_id`` 获取检测器，未注册返回 ``None``。"""
        return self._detectors.get(method_id)

    def list_all(self) -> list[PointTaskDetector]:
        """返回全部已注册检测器列表。"""
        return list(self._detectors.values())

    def list_metadata(self) -> list[dict[str, object]]:
        """返回全部检测器元数据列表，供前端配置时枚举可选项。"""
        return [d.metadata for d in self._detectors.values()]

    def clear(self) -> None:
        """清空注册表（主要用于测试）。"""
        self._detectors.clear()


#: 模块级单例
point_detector_registry = PointDetectorRegistry()


def register(detector: PointTaskDetector) -> None:
    """便捷函数：注册到全局注册表。"""
    point_detector_registry.register(detector)
