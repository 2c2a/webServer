"""旋转验证码（内外圈差速拼接版）。

设计：
* 外圈 = 灰底圆环 + 紫色三角标记（朝内指向圆心）
* 内圈 = 实心圆 + 绿色三角标记（朝外指向圆外）
* 后端把外圈预旋转 ``target_outer`` 度，内圈预旋转 ``target_inner`` 度
* 用户拖动滑块得到 angle（0~360）：
  - 外圈实时旋转 +angle  →  实际角度 = (target_outer + angle) mod 360
  - 内圈实时旋转 +2*angle →  实际角度 = (target_inner + 2*angle) mod 360
* 拼接条件：两个标记落在同一径向线上（角度相等，不限定方向）
  - target_outer + angle ≡ target_inner + 2*angle (mod 360)
  - → angle ≡ target_outer - target_inner (mod 360)
* 据此反解：随机选 angle_solution 与 target_outer，令
  target_inner = (target_outer - angle_solution) mod 360。
  这样每次外圈初始角、内圈初始角、拼接方向三者都随机。

差速旋转的妙处：单看任一圈都无法判断是否归位（标记会持续转动），
必须同时观察内外两圈；拼接方向也不固定，机器无法靠"找 12 点"破解。
"""
from __future__ import annotations

import secrets
import time

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.svg import wrap_svg


class RotateProvider(CaptchaProvider):
    """旋转拼接（外环 + 内圆 差速）。"""

    type_id = "rotate"
    name = "旋转拼接"
    description = "拖动滑块让内外圈标记对齐到同一方向"
    width = 300
    height = 180
    tolerance = 8.0  # 角度容差（度）
    ttl = 300
    max_attempts = 5

    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        # 用户需要拖动的角度（40~320 度，避免太靠近端点）
        angle_solution = secrets.randbelow(281) + 40
        # 外圈初始预旋转角度（完全随机）
        target_outer = secrets.randbelow(360)
        # 反推内圈初始角度，使 angle_solution 成为唯一解
        target_inner = (target_outer - angle_solution) % 360

        radius_outer = 82  # 外圈环半径
        radius_inner = 50  # 内圈圆半径
        cx = self.width // 2
        cy = self.height // 2

        outer_body = _render_outer_ring(cx, cy, radius_outer, radius_inner, target_outer)
        inner_body = _render_inner_disc(cx, cy, radius_inner, target_inner)
        outer_svg = wrap_svg(self.width, self.height, outer_body)
        inner_svg = wrap_svg(self.width, self.height, inner_body)

        return CaptchaChallenge(
            captcha_id=captcha_id,
            type=self.type_id,
            image=outer_svg,
            background=inner_svg,
            hint="请拖动滑块让内外圈标记对齐到同一方向",
            width=self.width,
            height=self.height,
            state={
                "angle_solution": angle_solution,
                "target_outer": target_outer,
                "target_inner": target_inner,
            },
            expires_at=time.time() + self.ttl,
            max_attempts=self.max_attempts,
            meta={"rotate_differential": True},
        )

    async def verify(
        self, challenge: CaptchaChallenge, answer: dict
    ) -> VerifyResult:
        angle = float(answer.get("angle", 0))
        target_outer = float(challenge.state["target_outer"])
        target_inner = float(challenge.state["target_inner"])
        # 外圈 / 内圈实际角度
        outer_actual = (target_outer + angle) % 360
        inner_actual = (target_inner + 2 * angle) % 360
        # 拼接条件：两个标记落在同一径向线上（角度差为 0）
        diff = (outer_actual - inner_actual) % 360
        diff = min(diff, 360 - diff)
        if diff > self.tolerance:
            return VerifyResult(
                success=False,
                message=f"内外圈未对齐（偏差 {diff:.0f}°）",
                need_refresh=diff > 60,
                remaining_attempts=_remaining(challenge),
            )
        return VerifyResult(success=True, message="验证成功")


def _render_outer_ring(
    cx: int, cy: int, r_outer: int, r_inner: int, target_angle: float
) -> str:
    """外圈：灰底圆环 + 12 点位置的紫色三角形（朝内指向圆心）。

    三角形被 ``<g transform="rotate(target_angle cx cy)">`` 包裹，
    故初始位置已偏移 ``target_angle`` 度。
    """
    # 三角顶点：略微伸入内圈边缘（让对齐时与内圈三角顶点接近）
    tip_y = cy - r_inner + 2
    # 三角底两点：略微超出外圈外侧
    base_y = cy - r_outer - 4
    half = 10
    return (
        # 灰底圆环（粗描边模拟环带）
        f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="none" '
        f'stroke="#e5e7eb" stroke-width="8"/>'
        # 圆环描边
        f'<circle cx="{cx}" cy="{cy}" r="{r_outer}" fill="none" '
        f'stroke="#9ca3af" stroke-width="1.5"/>'
        # 预旋转的紫色三角标记（朝内）
        f'<g transform="rotate({target_angle:.2f} {cx} {cy})">'
        f'<polygon points="{cx},{tip_y} {cx - half},{base_y} {cx + half},{base_y}" '
        f'fill="#4f46e5" stroke="#312e81" stroke-width="1"/>'
        f'</g>'
    )


def _render_inner_disc(
    cx: int, cy: int, r_inner: int, target_angle: float
) -> str:
    """内圈：实心圆 + 12 点位置的绿色三角形（朝外指向圆外）。

    与外圈三角顶点对齐时形成完整菱形，视觉上"拼接"成功。
    """
    # 三角顶点：略微超出圆外（与外圈三角顶点接近）
    tip_y = cy - r_inner - 4
    # 三角底两点：在圆内
    base_y = cy - r_inner + 14
    half = 10
    grad_id = "ig_rotate"
    return (
        f'<defs>'
        f'<radialGradient id="{grad_id}" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0%" stop-color="#bbf7d0"/>'
        f'<stop offset="100%" stop-color="#10b981"/>'
        f'</radialGradient>'
        f'</defs>'
        # 实心圆
        f'<circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="url(#{grad_id})"/>'
        # 圆描边
        f'<circle cx="{cx}" cy="{cy}" r="{r_inner}" fill="none" '
        f'stroke="#047857" stroke-width="1.5"/>'
        # 预旋转的绿色三角标记（朝外）
        f'<g transform="rotate({target_angle:.2f} {cx} {cy})">'
        f'<polygon points="{cx},{tip_y} {cx - half},{base_y} {cx + half},{base_y}" '
        f'fill="#10b981" stroke="#064e3b" stroke-width="1"/>'
        f'</g>'
    )


def _remaining(challenge: CaptchaChallenge) -> int:
    return max(challenge.max_attempts - challenge.attempts - 1, 0)
