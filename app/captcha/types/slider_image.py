"""滑块拼图验证码。

经典 jigsaw 拼图：从背景图中挖出一块，用户拖动拼图块到缺口位置填满。
校验：滑块释放 X 坐标与缺口 X 坐标的差值 ≤ 容差。

参考 tianai.cloud 的 ``slider_image`` 类型。
"""
from __future__ import annotations

import secrets
import time

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.svg import jigsaw_piece_path, make_background, wrap_svg
from app.captcha.svg import to_data_uri


class SliderImageProvider(CaptchaProvider):
    """滑块拼图（jigsaw puzzle）。"""

    type_id = "slider_image"
    name = "滑块拼图"
    description = "拖动拼图块填满缺口"
    width = 320
    height = 180
    tolerance = 6.0  # 像素容差
    ttl = 300
    max_attempts = 5

    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        # 拼图块尺寸
        piece_w = 50
        piece_h = 50
        # 拼图块初始位置：左端外露（用户可拖动）
        piece_x0 = 10
        # 拼图块满程位移（SVG 坐标空间）：滑块 0→1 时拼图块 0→full_travel
        full_travel = self.width - piece_w - piece_x0

        # ── 分段线性随机映射（反爬核心）──
        # f(0)=0, f(1)=1 端点固定：滑块拖到底拼图块必到最右，用户体验不受影响。
        # 中间 N 段交替"猛冲/卡住"：奇数段斜率高（拼图块快进），
        # 偶数段斜率低（拼图块几乎停滞），相邻段反差最大化，
        # 拖动时拼图块呈现明显的"一顿一冲"节奏感。
        N = 6  # 段数（5 个折点）
        rng = secrets.SystemRandom()
        slopes = []
        for k in range(N):
            if k % 2 == 0:
                slopes.append(rng.uniform(2.5, 4.0))  # 猛冲段
            else:
                slopes.append(rng.uniform(0.05, 0.3))  # 卡住段
        rng.shuffle(slopes)  # 打乱顺序，避免总是"冲-卡-冲-卡"
        total = sum(slopes) or 1.0
        ys: list[float] = [0.0]
        acc = 0.0
        for s in slopes:
            acc += s
            ys.append(round(acc / total, 4))
        ys[-1] = 1.0  # 规避浮点误差

        # 缺口 x：在拼图块可达范围 [margin, full_travel - margin] 内
        # 拼图块初始 SVG x=0，满程 x=full_travel，留边距避免太靠边
        gap_margin = 20
        gap_x = secrets.randbelow(int(full_travel) - 2 * gap_margin + 1) + gap_margin
        gap_y = secrets.randbelow(self.height - piece_h - 20) + 10
        piece_y0 = gap_y  # 与缺口同高，简化交互

        # 生成背景图（含拼图块挖空效果）
        bg_svg = make_background(self.width, self.height, seed=captcha_id + ":bg")
        # ── 不规则拼图块形状 ──
        # 每条边随机凸/凹，每条边凸凹幅度独立随机，每题形状不同。
        # 缺口与拼图块共用同一组参数（形状相同才能拼合）。
        rng = secrets.SystemRandom()
        edges = tuple(rng.choice([True, False]) for _ in range(4))
        tab_sizes = tuple(round(rng.uniform(7, 16), 2) for _ in range(4))
        # 在背景上挖出缺口（用透明孔洞）
        gap_path = jigsaw_piece_path(
            gap_x, gap_y, piece_w, piece_h, edges=edges, tab_sizes=tab_sizes
        )
        # 拼图块（带描边），形状与缺口一致
        piece_path = jigsaw_piece_path(
            0, 0, piece_w, piece_h, edges=edges, tab_sizes=tab_sizes
        )

        # 主图：背景 + 缺口（不含拼图块，拼图块单独作为可移动层）
        main_body = (
            f'<defs>'
            f'<mask id="gap-mask">'
            f'<rect width="{self.width}" height="{self.height}" fill="white"/>'
            f'<path d="{gap_path}" fill="black"/>'
            f'</mask>'
            f'</defs>'
            f'<image x="0" y="0" width="{self.width}" height="{self.height}" '
            f'href="{to_data_uri(bg_svg)}" mask="url(#gap-mask)"/>'
            f'<path d="{gap_path}" fill="none" stroke="rgba(0,0,0,0.35)" '
            f'stroke-width="1.5" stroke-dasharray="2,2"/>'
        )
        main_svg = wrap_svg(self.width, self.height, main_body)

        # 拼图块层：透明背景，仅含拼图块（位于 0,0，由前端 CSS transform 移动）
        piece_body = (
            f'<defs>'
            f'<clipPath id="piece-clip">'
            f'<path d="{piece_path}"/>'
            f'</clipPath>'
            f'</defs>'
            f'<g transform="translate(0,{piece_y0})">'
            f'<image x="{-gap_x}" y="{-gap_y}" '
            f'width="{self.width}" height="{self.height}" '
            f'href="{to_data_uri(bg_svg)}" clip-path="url(#piece-clip)"/>'
            f'<path d="{piece_path}" fill="none" '
            f'stroke="rgba(255,255,255,0.6)" stroke-width="1"/>'
            f'</g>'
        )
        piece_svg = wrap_svg(self.width, self.height, piece_body)

        return CaptchaChallenge(
            captcha_id=captcha_id,
            type=self.type_id,
            image=main_svg,
            background=piece_svg,  # 拼图块作为可移动层
            hint="请拖动左侧拼图块填满缺口",
            width=self.width,
            height=self.height,
            state={
                "gap_x": gap_x,
                "gap_y": gap_y,
                "piece_w": piece_w,
                "piece_h": piece_h,
                "piece_x0": piece_x0,
                "piece_y0": piece_y0,
            },
            expires_at=time.time() + self.ttl,
            max_attempts=self.max_attempts,
            # 暴露给前端的分段线性映射控制点（不敏感）：
            # f(r) = 分段线性插值，r ∈ [0,1] 为滑块比例，返回拼图块比例
            # ys = [0, y1, y2, ..., 1]，x 等距 N 段
            meta={"ys": ys, "segments": N},
        )

    async def verify(
        self, challenge: CaptchaChallenge, answer: dict
    ) -> VerifyResult:
        # 前端已把滑块像素位移映射为 SVG 坐标空间的拼图块 X
        x = float(answer.get("x", 0))
        gap_x = float(challenge.state["gap_x"])
        diff = abs(x - gap_x)
        if diff > self.tolerance:
            return VerifyResult(
                success=False,
                message=f"拼图块位置偏差 {diff:.0f}px",
                need_refresh=diff > 30,
                remaining_attempts=_remaining(challenge),
            )
        return VerifyResult(success=True, message="验证成功")


def _remaining(challenge: CaptchaChallenge) -> int:
    return max(challenge.max_attempts - challenge.attempts - 1, 0)
