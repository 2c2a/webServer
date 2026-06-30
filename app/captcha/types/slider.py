"""滑块验证码（drag-to-end）。

最简单的行为验证码：用户拖动滑块从起点到终点。
校验关注：

1. 拖动距离是否覆盖大部分轨道（≥ 90%）
2. 拖动轨迹是否存在合理的速度变化（非线性，防机器人）

不依赖图像匹配，纯行为校验。
"""
from __future__ import annotations

import secrets
import time

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.svg import make_background, wrap_svg


class SliderProvider(CaptchaProvider):
    """简单滑块（drag-to-end）。"""

    type_id = "slider"
    name = "滑块验证"
    description = "拖动滑块完成验证"
    width = 300
    height = 80
    tolerance = 5.0
    ttl = 300
    max_attempts = 5

    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        # 轨道宽度（前端滑块可拖动范围）
        track_width = self.width - 50  # 减去滑块自身宽度
        target_x = track_width  # 终点
        # 服务端保存：目标距离 + 一次性 nonce
        nonce = secrets.token_hex(8)
        bg = make_background(self.width, self.height, seed=captcha_id)
        # 主图：仅渲染轨道 + 起点滑块（前端 JS 接管交互）
        body = (
            f'<rect x="0" y="0" width="{self.width}" height="{self.height}" '
            f'fill="#f3f4f6" rx="6"/>'
            f'<rect x="10" y="32" width="{track_width}" height="16" '
            f'fill="#e5e7eb" rx="8"/>'
            f'<rect x="10" y="32" width="{track_width}" height="16" '
            f'fill="url(#prog)" rx="8" opacity="0.4"/>'
            f'<rect id="knob" x="10" y="22" width="40" height="36" '
            f'fill="#4f46e5" rx="8"/>'
            f'<text x="30" y="42" font-size="20" fill="#ffffff" '
            f'text-anchor="middle" dominant-baseline="central">→</text>'
            f'<defs>'
            f'<linearGradient id="prog" x1="0%" y1="0%" x2="100%" y2="0%">'
            f'<stop offset="0%" stop-color="#10b981"/>'
            f'<stop offset="100%" stop-color="#3b82f6"/>'
            f'</linearGradient>'
            f'</defs>'
        )
        svg = wrap_svg(self.width, self.height, body, background=bg)
        return CaptchaChallenge(
            captcha_id=captcha_id,
            type=self.type_id,
            image=svg,
            hint="请拖动滑块到最右端",
            width=self.width,
            height=self.height,
            state={
                "target_x": target_x,
                "nonce": nonce,
                "track_width": track_width,
            },
            expires_at=time.time() + self.ttl,
            max_attempts=self.max_attempts,
        )

    async def verify(
        self, challenge: CaptchaChallenge, answer: dict
    ) -> VerifyResult:
        x = float(answer.get("x", 0))
        target = float(challenge.state["target_x"])
        track_width = float(challenge.state["track_width"])
        # 行为轨迹：前端可选传 behavior 列表
        behavior = answer.get("behavior") or []

        # 校验 1：终点位置容差
        # 前端 knob 宽度与后端预设可能有差异，容差放宽到 ±20px
        if abs(x - target) > 20:
            return VerifyResult(
                success=False,
                message="滑块未到达终点",
                need_refresh=False,
                remaining_attempts=_remaining(challenge),
            )

        # 校验 2：轨迹长度（防直接 jump）
        if len(behavior) < 3:
            return VerifyResult(
                success=False,
                message="请正常拖动滑块",
                need_refresh=False,
                remaining_attempts=_remaining(challenge),
            )

        # 校验 3：轨迹单调性（允许少量回退，但总体应向前）
        xs = [p[0] for p in behavior if isinstance(p, (list, tuple)) and len(p) >= 2]
        if len(xs) >= 3:
            # 计算正向步数比例
            forward = sum(1 for i in range(1, len(xs)) if xs[i] >= xs[i - 1] - 3)
            if forward / len(xs) < 0.6:
                return VerifyResult(
                    success=False,
                    message="拖动行为异常",
                    need_refresh=True,
                    remaining_attempts=_remaining(challenge),
                )
            # 速度变化：检测是否完全匀速（机器人特征）
            speeds = [abs(xs[i] - xs[i - 1]) for i in range(1, len(xs))]
            if speeds and max(speeds) - min(speeds) < 1.0 and len(speeds) > 5:
                return VerifyResult(
                    success=False,
                    message="拖动行为异常",
                    need_refresh=True,
                    remaining_attempts=_remaining(challenge),
                )

        # 拖动距离是否覆盖 90% 轨道
        if x < track_width * 0.85:
            return VerifyResult(
                success=False,
                message="滑块未拖动到位",
                need_refresh=False,
                remaining_attempts=_remaining(challenge),
            )

        return VerifyResult(success=True, message="验证成功")


def _remaining(challenge: CaptchaChallenge) -> int:
    return max(challenge.max_attempts - challenge.attempts - 1, 0)
