"""行为验证码基类与数据结构。

验证码提供者（:class:`CaptchaProvider`）需要回答两个问题：

1. 生成一道题目（:meth:`generate`），返回图片数据 + 提示文本 + 服务端状态
2. 校验用户答案（:meth:`verify`），返回是否通过

设计原则：

* 图片采用 SVG 矢量格式生成（无 PIL 依赖、自适缩放、文件小）
* 服务端状态（``state``）写入 Redis，``captcha_id`` 作为键
* 一次性消费：验证成功 / 失败达上限后立即作废
* 容差判定：滑块、旋转、点选均允许像素/角度容差，避免苛刻
* 行为可选分析：``behavior`` 字段携带轨迹数据，可用于反爬升级
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaptchaChallenge:
    """一道验证码题目。

    Attributes
    ----------
    captcha_id:
        全局唯一 ID（用作 Redis 键）。
    type:
        验证码类型 ID，对应 :attr:`CaptchaProvider.type_id`。
    image:
        主图 SVG 内容（或 data URI），前端直接渲染。
    background:
        滑块拼图等类型的背景图（可为空）。
    hint:
        用户提示文本，例如 ``"请按顺序点击：山 河 大 地"``。
    width / height:
        图片逻辑尺寸（SVG viewBox）。
    state:
        服务端私有状态（含答案 + 元数据），**绝不返回给前端**。
    expires_at:
        过期 Unix 时间戳。
    max_attempts:
        最大尝试次数。
    """

    captcha_id: str
    type: str
    image: str
    hint: str = ""
    background: str | None = None
    width: int = 300
    height: int = 180
    state: dict[str, Any] = field(default_factory=dict)
    expires_at: float = 0.0
    max_attempts: int = 5
    # 点选类预期点击次数（0 表示由前端推断 / 不限制）
    expected_clicks: int = 0
    # 前端可见的额外元数据（不敏感），如滑块拼图的随机速度系数
    meta: dict[str, Any] = field(default_factory=dict)
    # 运行时字段（不返回给前端）
    attempts: int = 0
    verified: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        """返回前端可见字段（剥离 state）。"""
        return {
            "captcha_id": self.captcha_id,
            "type": self.type,
            "image": self.image,
            "background": self.background,
            "hint": self.hint,
            "width": self.width,
            "height": self.height,
            "expires_at": self.expires_at,
            "expected_clicks": self.expected_clicks,
            "meta": self.meta,
        }


@dataclass
class VerifyResult:
    """验证结果。"""

    success: bool
    message: str = ""
    need_refresh: bool = False
    remaining_attempts: int = 0


class CaptchaProvider(abc.ABC):
    """验证码提供者抽象基类。

    子类必须设置 :attr:`type_id` 与 :attr:`name`，并实现 :meth:`generate`
    与 :meth:`verify` 两个异步方法。

    ``type_id`` 与 ``CaptchaChallenge.type`` 一一对应，用于在注册表中查找。
    """

    #: 类型唯一标识，如 ``slider_image``
    type_id: str = ""
    #: 显示名称，如 ``滑块拼图``
    name: str = ""
    #: 描述
    description: str = ""
    #: 图片宽度
    width: int = 300
    #: 图片高度
    height: int = 180
    #: 默认容差（像素 / 角度，由子类解释）
    tolerance: float = 5.0
    #: 默认有效期（秒）
    ttl: int = 300
    #: 默认最大尝试次数
    max_attempts: int = 5

    @abc.abstractmethod
    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        """生成一道题目。"""
        ...

    @abc.abstractmethod
    async def verify(
        self, challenge: CaptchaChallenge, answer: dict[str, Any]
    ) -> VerifyResult:
        """校验用户答案。

        ``answer`` 由前端提交，常见字段：
        * ``x`` / ``y``：滑块释放位置、点选坐标
        * ``angle``：旋转角度
        * ``points``：点选坐标列表 ``[[x, y], ...]``
        * ``behavior``：行为轨迹（可选，用于反爬分析）
        """
        ...

    @property
    def metadata(self) -> dict[str, Any]:
        """元数据，供前端展示与配置。"""
        return {
            "type_id": self.type_id,
            "name": self.name,
            "description": self.description,
            "width": self.width,
            "height": self.height,
        }
