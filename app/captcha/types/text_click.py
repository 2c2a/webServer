"""文字点选验证码。

在图片中放置 3~5 个汉字（随机字体大小 / 旋转 / 颜色），
提示用户按指定顺序点击。校验：点击坐标是否落在对应汉字的包围盒内，
顺序必须匹配。

使用 Pillow 渲染为 PNG，精确控制旋转后边界，确保不出画布。

参考 tianai.cloud 的 ``click`` 类型。
"""
from __future__ import annotations

import base64
import secrets
import time

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.image import render_text_captcha
from app.captcha.wordpool import HANZI_LIST


class TextClickProvider(CaptchaProvider):
    """文字点选（按显示顺序点击）。"""

    type_id = "text_click"
    name = "文字点选"
    description = "按顺序点击图中文字"
    width = 300
    height = 180
    tolerance = 22.0  # 点击坐标容差（像素）
    ttl = 300
    max_attempts = 5

    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        n = 3  # 每题 3 个字
        chosen = secrets.SystemRandom().sample(HANZI_LIST, n)
        # 用户需按提示顺序点击，提示顺序 = 随机打乱
        order = list(range(n))
        secrets.SystemRandom().shuffle(order)
        hint_chars = [chosen[i] for i in order]

        # 排布位置（Pillow 会自动裁剪到画布内，margin 适中即可）
        positions: list[tuple[float, float]] = []
        attempts = 0
        margin = 48
        while len(positions) < n and attempts < 200:
            x = secrets.randbelow(self.width - 2 * margin) + margin
            y = secrets.randbelow(self.height - 2 * margin) + margin
            if all((x - px) ** 2 + (y - py) ** 2 > 60 ** 2 for px, py in positions):
                positions.append((x, y))
            attempts += 1
        while len(positions) < n:
            positions.append((margin + 60 * len(positions), self.height // 2))

        # 构造渲染参数：大旋转 + 随机颜色
        items = []
        for i, char in enumerate(chosen):
            x, y = positions[i]
            size = secrets.randbelow(8) + 24  # 24~32
            rot = secrets.randbelow(180) - 90  # -90~90 度，极限旋转
            items.append({"char": char, "x": x, "y": y, "size": size, "rotation": rot})

        # Pillow 渲染（CPU 密集 ~0.2s，直接同步调用）
        png_bytes, boxes = render_text_captcha(
            self.width, self.height, items, seed=captcha_id + ":tc",
        )
        image_data_uri = (
            "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
        )

        hint = "请依次点击：" + " ".join(hint_chars)

        return CaptchaChallenge(
            captcha_id=captcha_id,
            type=self.type_id,
            image=image_data_uri,
            hint=hint,
            width=self.width,
            height=self.height,
            state={
                "chars": chosen,            # 图上顺序
                "boxes": boxes,             # 每个字的实际包围盒（Pillow 计算）
                "expected_order": order,    # 用户点击顺序（索引到 chosen）
            },
            expires_at=time.time() + self.ttl,
            max_attempts=self.max_attempts,
            expected_clicks=len(chosen),
        )

    async def verify(
        self, challenge: CaptchaChallenge, answer: dict
    ) -> VerifyResult:
        points = answer.get("points") or []
        expected = challenge.state["expected_order"]
        boxes = challenge.state["boxes"]

        if len(points) != len(expected):
            return VerifyResult(
                success=False,
                message=f"请点击 {len(expected)} 个字",
                remaining_attempts=_remaining(challenge),
            )

        # 逐个校验：第 i 次点击应落在 boxes[expected[i]] 的包围盒内（带容差）
        tol = self.tolerance
        for i, pt in enumerate(points):
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                return VerifyResult(
                    success=False,
                    message="点击坐标格式错误",
                    remaining_attempts=_remaining(challenge),
                )
            px, py = float(pt[0]), float(pt[1])
            idx = expected[i]
            x1, y1, x2, y2 = boxes[idx]
            if not (x1 - tol <= px <= x2 + tol and y1 - tol <= py <= y2 + tol):
                return VerifyResult(
                    success=False,
                    message=f"第 {i + 1} 个字点击错误",
                    need_refresh=False,
                    remaining_attempts=_remaining(challenge),
                )
        return VerifyResult(success=True, message="验证成功")


def _remaining(challenge: CaptchaChallenge) -> int:
    return max(challenge.max_attempts - challenge.attempts - 1, 0)
