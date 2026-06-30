"""语序点选验证码。

与文字点选类似，但题目来源是成语 / 诗句，提示文本为"请按 X 的顺序点击"。
用户必须在图中按 X 的字序点击对应字符。

使用 Pillow 渲染为 PNG，精确控制旋转后边界，确保不出画布。

参考 tianai.cloud 的 ``sequence_click`` 类型。
"""
from __future__ import annotations

import base64
import secrets
import time

from app.captcha.base import CaptchaChallenge, CaptchaProvider, VerifyResult
from app.captcha.image import render_text_captcha
from app.captcha.wordpool import HANZI_LIST, IDIOM_POOL


class SequenceClickProvider(CaptchaProvider):
    """语序点选（成语 / 诗句顺序）。"""

    type_id = "sequence_click"
    name = "语序点选"
    description = "按成语/诗句顺序点击图中文字"
    width = 300
    height = 180
    tolerance = 22.0
    ttl = 300
    max_attempts = 5

    async def generate(self, captcha_id: str) -> CaptchaChallenge:
        # 选一个 4~5 字的成语 / 诗句
        # 过滤掉含重复字的成语：同字在图中无法区分，会导致语序校验歧义
        candidates = [s for s in IDIOM_POOL if 4 <= len(s) <= 5 and len(set(s)) == len(s)]
        phrase = secrets.choice(candidates)
        chars = list(phrase)
        n = len(chars)

        # 在池中再加几个干扰字（避免同字重复出现）
        distractors: list[str] = []
        existing = set(chars)
        while len(distractors) < 2:
            cand = secrets.choice(HANZI_LIST)
            if cand not in existing:
                distractors.append(cand)
                existing.add(cand)
        all_chars = chars + distractors  # 总共 n+2 个字
        # 打乱位置
        order_on_image = list(range(len(all_chars)))
        secrets.SystemRandom().shuffle(order_on_image)
        shuffled = [all_chars[i] for i in order_on_image]
        # 图上字符 -> 在 phrase 中的索引（干扰字为 -1）
        # 因已过滤重复字，chars.index(c) 唯一确定
        char_to_phrase_idx: list[int] = [
            chars.index(c) if c in chars else -1 for c in shuffled
        ]

        # 排布位置（Pillow 自动裁剪到画布内，margin 适中即可）
        positions: list[tuple[float, float]] = []
        attempts = 0
        margin = 42
        while len(positions) < len(shuffled) and attempts < 300:
            x = secrets.randbelow(self.width - 2 * margin) + margin
            y = secrets.randbelow(self.height - 2 * margin) + margin
            if all((x - px) ** 2 + (y - py) ** 2 > 48 ** 2 for px, py in positions):
                positions.append((x, y))
            attempts += 1
        while len(positions) < len(shuffled):
            positions.append((margin + 45 * len(positions), self.height // 2))

        # 构造渲染参数：大旋转
        items = []
        for i, char in enumerate(shuffled):
            x, y = positions[i]
            size = secrets.randbelow(8) + 26  # 26~34，更大字号更清晰
            rot = secrets.randbelow(180) - 90  # -90~90 度，极限旋转
            items.append({"char": char, "x": x, "y": y, "size": size, "rotation": rot})

        # Pillow 渲染（CPU 密集 ~0.2s，直接同步调用）
        png_bytes, boxes = render_text_captcha(
            self.width, self.height, items, seed=captcha_id + ":sc",
        )
        image_data_uri = (
            "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
        )

        # 不直接显示成语答案，迫使用户自行识别图中文字并排列成成语
        hint = "请按图中文字组成成语的正确顺序点击"

        return CaptchaChallenge(
            captcha_id=captcha_id,
            type=self.type_id,
            image=image_data_uri,
            hint=hint,
            width=self.width,
            height=self.height,
            state={
                "phrase": phrase,
                "shuffled": shuffled,
                "boxes": boxes,
                "char_to_phrase_idx": char_to_phrase_idx,
            },
            expires_at=time.time() + self.ttl,
            max_attempts=self.max_attempts,
            expected_clicks=len(phrase),
        )

    async def verify(
        self, challenge: CaptchaChallenge, answer: dict
    ) -> VerifyResult:
        points = answer.get("points") or []
        phrase = challenge.state["phrase"]
        boxes = challenge.state["boxes"]
        mapping = challenge.state["char_to_phrase_idx"]

        if len(points) != len(phrase):
            return VerifyResult(
                success=False,
                message=f"需要点击 {len(phrase)} 个字",
                remaining_attempts=_remaining(challenge),
            )

        tol = self.tolerance
        # 第 i 次点击：在所有命中（带容差）的 box 中取离点击点最近的一个，
        # 并检查其 mapping 是否等于 i。
        # box 之间因容差会重叠，"取最近"避免误判到邻近字符。
        used: set[int] = set()  # 已被命中的 box 索引，避免同一点击重复命中
        for i, pt in enumerate(points):
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                return VerifyResult(
                    success=False,
                    message="点击坐标格式错误",
                    remaining_attempts=_remaining(challenge),
                )
            px, py = float(pt[0]), float(pt[1])
            hits: list[tuple[float, int]] = []
            for j, (x1, y1, x2, y2) in enumerate(boxes):
                if j in used:
                    continue
                if x1 - tol <= px <= x2 + tol and y1 - tol <= py <= y2 + tol:
                    cx = (x1 + x2) / 2
                    cy = (y1 + y2) / 2
                    dist2 = (px - cx) ** 2 + (py - cy) ** 2
                    hits.append((dist2, j))
            if not hits:
                return VerifyResult(
                    success=False,
                    message=f"第 {i + 1} 个字未点中任何字符",
                    remaining_attempts=_remaining(challenge),
                )
            hits.sort()
            hit_idx = hits[0][1]
            if mapping[hit_idx] != i:
                return VerifyResult(
                    success=False,
                    message=f"第 {i + 1} 个字点错",
                    remaining_attempts=_remaining(challenge),
                )
            used.add(hit_idx)
        return VerifyResult(success=True, message="验证成功")


def _remaining(challenge: CaptchaChallenge) -> int:
    return max(challenge.max_attempts - challenge.attempts - 1, 0)
