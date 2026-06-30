"""区域点选验证码。

在画布上散布多种形状（不同颜色 / 形状 / 大小），提示用户点击所有
"X 颜色的 Y 形状"。校验：点击的所有点必须落在符合条件的形状包围盒内，
且数量匹配。

参考 tianai.cloud 的 ``region_click`` 类型。
"""
from __future__ import annotations

import secrets
import time

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.svg import (
    SHAPES,
    make_background,
    random_palette,
    shape_svg,
    wrap_svg,
)
from app.captcha.wordpool import COLOR_HEX, COLOR_WORDS, SHAPE_KIND, SHAPE_WORDS


class RegionClickProvider(CaptchaProvider):
    """区域点选（点击所有目标形状）。"""

    type_id = "region_click"
    name = "区域点选"
    description = "点击图中所有目标形状"
    width = 300
    height = 180
    tolerance = 18.0
    ttl = 300
    max_attempts = 5

    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        total = 8  # 总形状数
        # 目标：颜色 + 形状
        target_color = secrets.choice(COLOR_WORDS)
        target_shape = secrets.choice(SHAPE_WORDS)
        # 生成形状列表：保证有 2~3 个目标
        target_count = secrets.randbelow(2) + 2  # 2~3 个

        shapes_meta: list[dict] = []
        # 先放目标
        for _ in range(target_count):
            shapes_meta.append(
                {"color": target_color, "shape": target_shape, "size": 16}
            )
        # 再放干扰
        while len(shapes_meta) < total:
            c = secrets.choice(COLOR_WORDS)
            s = secrets.choice(SHAPE_WORDS)
            # 避免与目标完全相同
            if c == target_color and s == target_shape:
                continue
            shapes_meta.append({"color": c, "shape": s, "size": 16})

        secrets.SystemRandom().shuffle(shapes_meta)

        # 排布位置（不重叠）
        positions: list[tuple[float, float]] = []
        margin = 30
        attempts = 0
        while len(positions) < total and attempts < 300:
            x = secrets.randbelow(self.width - 2 * margin) + margin
            y = secrets.randbelow(self.height - 2 * margin) + margin
            if all((x - px) ** 2 + (y - py) ** 2 > 45 ** 2 for px, py in positions):
                positions.append((x, y))
            attempts += 1
        while len(positions) < total:
            positions.append((margin + 35 * len(positions), self.height // 2))

        # 渲染
        bodies = []
        boxes: list[tuple[float, float, float, float, bool]] = []  # x1,y1,x2,y2,is_target
        for i, m in enumerate(shapes_meta):
            x, y = positions[i]
            size = m["size"]
            color_hex = COLOR_HEX[m["color"]]
            kind = SHAPE_KIND[m["shape"]]
            rot = secrets.randbelow(60) - 30
            bodies.append(shape_svg(kind, x, y, size, color=color_hex, rotation=rot))
            is_target = m["color"] == target_color and m["shape"] == target_shape
            boxes.append((x - size - 4, y - size - 4, x + size + 4, y + size + 4, is_target))

        bg = make_background(self.width, self.height, seed=captcha_id + ":rc")
        body = "".join(bodies)
        svg = wrap_svg(self.width, self.height, body, background=bg)

        hint = f"请点击所有 {target_color} 的 {target_shape}"

        return CaptchaChallenge(
            captcha_id=captcha_id,
            type=self.type_id,
            image=svg,
            hint=hint,
            width=self.width,
            height=self.height,
            state={
                "target_color": target_color,
                "target_shape": target_shape,
                "target_count": target_count,
                "boxes": [b[:4] for b in boxes],  # 不暴露 is_target
                "target_boxes": [b[:4] for b in boxes if b[4]],
            },
            expires_at=time.time() + self.ttl,
            max_attempts=self.max_attempts,
            expected_clicks=target_count,
        )

    async def verify(
        self, challenge: CaptchaChallenge, answer: dict
    ) -> VerifyResult:
        points = answer.get("points") or []
        target_count = int(challenge.state["target_count"])
        target_boxes = challenge.state["target_boxes"]
        all_boxes = challenge.state["boxes"]

        if len(points) != target_count:
            return VerifyResult(
                success=False,
                message=f"需要点击 {target_count} 个目标",
                remaining_attempts=_remaining(challenge),
            )

        tol = self.tolerance
        # 每个目标必须被点中（点与目标一一对应，不允许重复）
        matched_targets = [False] * len(target_boxes)
        for pt in points:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                return VerifyResult(
                    success=False,
                    message="点击坐标格式错误",
                    remaining_attempts=_remaining(challenge),
                )
            px, py = float(pt[0]), float(pt[1])
            # 不能点中非目标
            for x1, y1, x2, y2 in all_boxes:
                if x1 - tol <= px <= x2 + tol and y1 - tol <= py <= y2 + tol:
                    # 落在某个盒子里，检查是否目标
                    for ti, (tx1, ty1, tx2, ty2) in enumerate(target_boxes):
                        if (
                            tx1 - tol <= px <= tx2 + tol
                            and ty1 - tol <= py <= ty2 + tol
                            and not matched_targets[ti]
                        ):
                            matched_targets[ti] = True
                            break
                    else:
                        return VerifyResult(
                            success=False,
                            message="点击了非目标形状",
                            remaining_attempts=_remaining(challenge),
                        )
                    break
            else:
                return VerifyResult(
                    success=False,
                    message="点击位置未命中任何形状",
                    remaining_attempts=_remaining(challenge),
                )

        if not all(matched_targets):
            return VerifyResult(
                success=False,
                message="还有目标未点击",
                remaining_attempts=_remaining(challenge),
            )
        return VerifyResult(success=True, message="验证成功")


def _remaining(challenge: CaptchaChallenge) -> int:
    return max(challenge.max_attempts - challenge.attempts - 1, 0)
