"""推理点选验证码。

在画布上放置若干形状（不同颜色 / 形状 / 大小），提示用户根据推理点击：
* "请点击最大的图形"
* "请点击红色的圆形"
* "请点击最小的形状"

形状中心对称，SVG 旋转不会出界，无需 Pillow。
网格排布避免随机重试导致性能问题。

参考 tianai.cloud 的 ``reasoning_click`` 类型。
"""
from __future__ import annotations

import secrets
import time

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.svg import make_background, shape_svg, wrap_svg
from app.captcha.wordpool import COLOR_HEX, COLOR_WORDS, SHAPE_KIND, SHAPE_WORDS


class ReasoningClickProvider(CaptchaProvider):
    """推理点选（基于属性推理）。"""

    type_id = "reasoning_click"
    name = "推理点选"
    description = "根据提示推理并点击对应图形"
    width = 300
    height = 180
    tolerance = 20.0
    ttl = 300
    max_attempts = 5

    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        total = 6
        dimension = secrets.choice(["size", "color", "shape"])

        shapes_meta: list[dict] = []
        if dimension == "size":
            color = secrets.choice(COLOR_WORDS)
            shape = secrets.choice(SHAPE_WORDS)
            sizes = [12, 16, 20, 24, 28, 32][:total]
            secrets.SystemRandom().shuffle(sizes)
            for s in sizes:
                shapes_meta.append({"color": color, "shape": shape, "size": s})
            target_idx = sizes.index(max(sizes))
            hint = "请点击最大的图形"
        elif dimension == "color":
            shape = secrets.choice(SHAPE_WORDS)
            size = 22
            colors = []
            while len(colors) < total:
                c = secrets.choice(COLOR_WORDS)
                if c not in colors:
                    colors.append(c)
            target_color = secrets.choice(colors)
            for c in colors:
                shapes_meta.append({"color": c, "shape": shape, "size": size})
            target_idx = colors.index(target_color)
            hint = f"请点击 {target_color} 的图形"
        else:
            color = secrets.choice(COLOR_WORDS)
            size = 22
            shape_list = []
            while len(shape_list) < total:
                s = secrets.choice(SHAPE_WORDS)
                if s not in shape_list:
                    shape_list.append(s)
            target_shape = secrets.choice(shape_list)
            for s in shape_list:
                shapes_meta.append({"color": color, "shape": s, "size": size})
            target_idx = shape_list.index(target_shape)
            hint = f"请点击 {target_shape}"

        # 网格排布：3 列 × 2 行，避免随机重试导致性能问题
        cols, rows = 3, 2
        cell_w = self.width / cols
        cell_h = self.height / rows
        positions: list[tuple[float, float]] = []
        for r in range(rows):
            for c in range(cols):
                jitter_x = secrets.randbelow(20) - 10
                jitter_y = secrets.randbelow(16) - 8
                positions.append(
                    (cell_w * (c + 0.5) + jitter_x, cell_h * (r + 0.5) + jitter_y)
                )
        secrets.SystemRandom().shuffle(positions)

        # SVG 渲染（与 region_click 一致，形状中心对称不会出界）
        bodies = []
        boxes: list[tuple[float, float, float, float]] = []
        for i, m in enumerate(shapes_meta):
            x, y = positions[i]
            size = m["size"]
            color_hex = COLOR_HEX[m["color"]]
            kind = SHAPE_KIND[m["shape"]]
            rot = secrets.randbelow(40) - 20
            bodies.append(shape_svg(kind, x, y, size, color=color_hex, rotation=rot))
            boxes.append((x - size - 6, y - size - 6, x + size + 6, y + size + 6))

        bg = make_background(self.width, self.height, seed=captcha_id + ":rcl")
        body = "".join(bodies)
        svg = wrap_svg(self.width, self.height, body, background=bg)

        return CaptchaChallenge(
            captcha_id=captcha_id,
            type=self.type_id,
            image=svg,
            hint=hint,
            width=self.width,
            height=self.height,
            state={
                "dimension": dimension,
                "target_idx": target_idx,
                "boxes": boxes,
            },
            expires_at=time.time() + self.ttl,
            max_attempts=self.max_attempts,
            expected_clicks=1,
        )

    async def verify(
        self, challenge: CaptchaChallenge, answer: dict
    ) -> VerifyResult:
        points = answer.get("points") or []
        if not points:
            x = answer.get("x")
            y = answer.get("y")
            if x is not None and y is not None:
                points = [[x, y]]
        if len(points) != 1:
            return VerifyResult(
                success=False,
                message="只能点击 1 个图形",
                remaining_attempts=_remaining(challenge),
            )

        pt = points[0]
        if not isinstance(pt, (list, tuple)) or len(pt) < 2:
            return VerifyResult(
                success=False,
                message="点击坐标格式错误",
                remaining_attempts=_remaining(challenge),
            )
        px, py = float(pt[0]), float(pt[1])
        target_idx = int(challenge.state["target_idx"])
        boxes = challenge.state["boxes"]
        tol = self.tolerance

        # 在所有命中（带容差）的 box 中取离点击点最近的一个
        hits: list[tuple[float, int]] = []
        for i, (x1, y1, x2, y2) in enumerate(boxes):
            if x1 - tol <= px <= x2 + tol and y1 - tol <= py <= y2 + tol:
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                dist2 = (px - cx) ** 2 + (py - cy) ** 2
                hits.append((dist2, i))
        if not hits:
            return VerifyResult(
                success=False,
                message="未点击目标图形",
                remaining_attempts=_remaining(challenge),
            )
        hits.sort()
        hit_idx = hits[0][1]
        if hit_idx != target_idx:
            return VerifyResult(
                success=False,
                message="点击了错误的图形",
                remaining_attempts=_remaining(challenge),
            )
        return VerifyResult(success=True, message="验证成功")


def _remaining(challenge: CaptchaChallenge) -> int:
    return max(challenge.max_attempts - challenge.attempts - 1, 0)
