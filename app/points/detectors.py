"""积分任务检测器基类与上下文。

检测器（:class:`PointTaskDetector`）负责回答两个问题：

1. 用户当前是否 *可* 完成此任务（:meth:`is_completable`），
   例如每日签到检测器会检查用户今天是否已签到；
2. 标记任务完成（:meth:`complete`），
   对于主动型任务（如签到）由前端调用，
   对于被动型任务（如工单提交）由系统在事件发生时调用。

内置检测器见 :mod:`app.points.builtin`，第三方检测器可通过
:func:`app.points.registry.register` 注册（典型场景为插件在
``on_load`` 钩子中注册）。
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.points import PointTask


@dataclass
class DetectorContext:
    """检测器执行上下文。

    Attributes
    ----------
    user_id:
        当前用户 ID。
    task:
        关联的积分任务（含 ``detection_method`` / ``config`` / ``points``）。
    site_group_id:
        当前租户站点组 ID（可为 ``None``）。
    db:
        异步数据库会话。
    extra:
        事件附带数据，例如工单提交检测器会传入 ``ticket`` 对象。
    """

    user_id: int
    task: PointTask
    site_group_id: int | None
    db: AsyncSession
    extra: dict | None = None


class PointTaskDetector(abc.ABC):
    """积分任务检测器抽象基类。

    子类必须设置类属性 :attr:`method_id` 与 :attr:`name`，并实现
    :meth:`is_completable` 与 :meth:`complete` 两个异步方法。

    ``method_id`` 与 :class:`PointTask.detection_method` 一一对应，
    用于在注册表中查找检测器。
    """

    #: 检测方式唯一标识，如 ``daily_checkin``
    method_id: str = ""
    #: 显示名称，如 ``每日签到``
    name: str = ""
    #: 描述
    description: str = ""
    #: 是否为被动触发（由系统事件驱动完成，而非用户主动调用）
    passive: bool = False

    @abc.abstractmethod
    async def is_completable(self, ctx: DetectorContext) -> bool:
        """检查用户当前是否可完成此任务。

        对于被动检测器（``passive=True``），通常返回 ``False`` ——
        完成由系统事件触发，不暴露给用户主动调用。
        """
        ...

    @abc.abstractmethod
    async def complete(self, ctx: DetectorContext) -> bool:
        """标记任务完成并返回是否成功。

        返回 ``True`` 表示完成成功，调用方据此发放积分；
        返回 ``False`` 表示不可完成或已完成（如今天已签到），不发放积分。

        实现不应自行写入积分流水，只负责自身的完成记录（如签到表），
        积分发放由 :mod:`app.points.service` 统一处理。
        """
        ...

    @property
    def metadata(self) -> dict[str, object]:
        """返回检测器元数据，用于前端展示与配置。"""
        return {
            "method_id": self.method_id,
            "name": self.name,
            "description": self.description,
            "passive": self.passive,
        }
