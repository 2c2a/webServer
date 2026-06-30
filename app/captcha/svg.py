"""SVG 验证码图片生成工具。

无 PIL 依赖，全部以矢量方式绘制：

* 背景：渐变 + 抽象几何噪声
* 拼图块：经典 4 凸 4 凹 jigsaw 边
* 文字：随机字体大小 / 旋转角度 / 颜色
* 形状：圆形 / 矩形 / 三角形 / 五角星

所有函数返回 ``str``（SVG 内容，可直接嵌入 HTML 或转为 data URI）。
"""
from __future__ import annotations

import math
import random
import secrets
from html import escape


# ──────────────────────────────────────────────────────────────
# 颜色工具
# ──────────────────────────────────────────────────────────────

#: 调色板（HSL 生成保证可读）
_PALETTE = [
    "#4F46E5", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444",
    "#8B5CF6", "#EC4899", "#14B8A6", "#F97316", "#84CC16",
    "#06B6D4", "#A855F7", "#EAB308", "#22C55E", "#3B82F6",
]


def random_color() -> str:
    return secrets.choice(_PALETTE)


def random_palette(n: int) -> list[str]:
    """返回 n 个不重复颜色（n 超过调色板时允许重复）。"""
    if n <= len(_PALETTE):
        return random.sample(_PALETTE, n)
    return [secrets.choice(_PALETTE) for _ in range(n)]


# ──────────────────────────────────────────────────────────────
# 背景：渐变 + 几何噪声
# ──────────────────────────────────────────────────────────────

def make_background(width: int, height: int, *, seed: str | None = None) -> str:
    """生成带渐变和噪声的背景 SVG。

    返回完整 ``<svg>`` 文档字符串。
    """
    rng = random.Random(seed)
    grad_id = f"g{rng.randrange(16**8):08x}"
    c1 = rng.choice(_PALETTE)
    c2 = rng.choice(_PALETTE)
    angle = rng.randint(0, 360)
    x2 = 50 + 50 * math.cos(math.radians(angle))
    y2 = 50 + 50 * math.sin(math.radians(angle))

    shapes: list[str] = []
    # 几何噪声：散布若干半透明圆形 / 线段，干扰 OCR
    for _ in range(18):
        x = rng.randint(0, width)
        y = rng.randint(0, height)
        r = rng.randint(6, 28)
        color = rng.choice(_PALETTE)
        opacity = rng.randint(30, 90) / 255
        if rng.random() < 0.5:
            shapes.append(
                f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}" '
                f'fill-opacity="{opacity:.2f}"/>'
            )
        else:
            x1 = rng.randint(0, width)
            y1 = rng.randint(0, height)
            x2p = rng.randint(0, width)
            y2p = rng.randint(0, height)
            shapes.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2p}" y2="{y2p}" '
                f'stroke="{color}" stroke-width="{rng.randint(1,3)}" '
                f'stroke-opacity="{opacity:.2f}"/>'
            )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        f'<defs>'
        f'<linearGradient id="{grad_id}" x1="0%" y1="0%" x2="{x2:.2f}%" y2="{y2:.2f}%">'
        f'<stop offset="0%" stop-color="{c1}"/>'
        f'<stop offset="100%" stop-color="{c2}"/>'
        f'</linearGradient>'
        f'</defs>'
        f'<rect width="{width}" height="{height}" fill="url(#{grad_id})"/>'
        f'{"".join(shapes)}'
        f'</svg>'
    )


# ──────────────────────────────────────────────────────────────
# 拼图块路径（4 凸 4 凹 jigsaw）
# ──────────────────────────────────────────────────────────────

def jigsaw_piece_path(
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    tab: float = 12.0,
    edges: tuple[bool, bool, bool, bool] | None = None,
    tab_sizes: tuple[float, float, float, float] | None = None,
) -> str:
    """生成拼图块 SVG path。

    起点 ``(x, y)``，宽高 ``w × h``，凸起高度 ``tab``。

    * ``edges``：4 条边是否凸起（True 凸 / False 凹），默认全凸。
    * ``tab_sizes``：每条边独立的凸/凹幅度，默认统一 ``tab``。
      两者均可随机生成，制造不规则形状。

    注意：缺口与拼图块必须用互补的 ``edges``（按位取反），
    否则无法拼合。
    """
    if edges is None:
        edges = (True, False, True, False)
    if tab_sizes is None:
        tab_sizes = (tab, tab, tab, tab)

    # 用贝塞尔曲线模拟凸/凹，每条边中间一段膨胀/收缩
    def edge(p0: tuple[float, float], p1: tuple[float, float], *, out: bool, t: float) -> str:
        """从 p0 走到 p1，中间凸(out=True) 或凹(out=False)，幅度 t。"""
        dx = p1[0] - p0[0]
        dy = p1[1] - p0[1]
        # 起止控制点：在边的 35% 与 65% 位置
        sx0 = p0[0] + dx * 0.35
        sy0 = p0[1] + dy * 0.35
        sx1 = p0[0] + dx * 0.65
        sy1 = p0[1] + dy * 0.65
        # 垂直方向（指向边外）
        nx = -dy / (math.hypot(dx, dy) or 1)
        ny = dx / (math.hypot(dx, dy) or 1)
        sign = 1 if out else -1
        # 控制点：在边中点法向偏移 ±1.2*t
        cx = (p0[0] + p1[0]) / 2 + nx * sign * t * 1.2
        cy = (p0[1] + p1[1]) / 2 + ny * sign * t * 1.2
        return (
            f"L {sx0:.2f} {sy0:.2f} "
            f"Q {cx:.2f} {cy:.2f} {sx1:.2f} {sy1:.2f} "
            f"L {p1[0]:.2f} {p1[1]:.2f}"
        )

    p0 = (x, y)
    p1 = (x + w, y)
    p2 = (x + w, y + h)
    p3 = (x, y + h)

    return (
        f"M {p0[0]:.2f} {p0[1]:.2f} "
        + edge(p0, p1, out=edges[0], t=tab_sizes[0]) + " "
        + edge(p1, p2, out=edges[1], t=tab_sizes[1]) + " "
        + edge(p2, p3, out=edges[2], t=tab_sizes[2]) + " "
        + edge(p3, p0, out=edges[3], t=tab_sizes[3]) + " "
        + "Z"
    )


# ──────────────────────────────────────────────────────────────
# 文字（点选验证码）
# ──────────────────────────────────────────────────────────────

def text_glyph(
    char: str,
    x: float,
    y: float,
    *,
    size: int = 28,
    color: str | None = None,
    rotation: float = 0.0,
    skew_x: float = 0.0,
    skew_y: float = 0.0,
    font_family: str = "system-ui, sans-serif",
    stroke: bool = False,
) -> str:
    """渲染单个汉字 / 字符为 SVG ``<text>`` 元素。

    支持旋转 + 双向倾斜（skew）扭曲，可选描边干扰，提升 OCR 难度。
    """
    color = color or random_color()
    # 组合变换：先以 (x, y) 为中心 skew，再 rotate
    parts: list[str] = []
    if rotation:
        parts.append(f"rotate({rotation:.2f} {x:.2f} {y:.2f})")
    if skew_x or skew_y:
        # 以 (x, y) 为锚点的 skewX(α)·skewY(β) 复合矩阵
        # matrix(1 tan(β) tan(α) 1  cx-tan(α)*cy  cy-tan(β)*cx)
        ta, tb = skew_x, skew_y
        e = x - ta * y
        f_ = y - tb * x
        parts.append(f"matrix(1 {tb:.3f} {ta:.3f} 1 {e:.2f} {f_:.2f})")
    transform = f'transform="{" ".join(parts)}"' if parts else ""
    stroke_attr = (
        f'stroke="{color}" stroke-width="0.8" paint-order="stroke" '
        if stroke else ""
    )
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
        f'font-family="{font_family}" font-weight="600" '
        f'fill="{color}" {stroke_attr}text-anchor="middle" '
        f'dominant-baseline="central" {transform}>'
        f'{escape(char)}</text>'
    )


# ──────────────────────────────────────────────────────────────
# 形状（区域点选 / 推理点选）
# ──────────────────────────────────────────────────────────────

def shape_svg(
    kind: str,
    x: float,
    y: float,
    size: float,
    *,
    color: str | None = None,
    rotation: float = 0.0,
) -> str:
    """渲染一个形状。

    kind ∈ ``circle`` | ``square`` | ``triangle`` | ``star``
    """
    color = color or random_color()
    transform = (
        f'transform="rotate({rotation:.2f} {x:.2f} {y:.2f})"'
        if rotation else ""
    )
    if kind == "circle":
        return (
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size:.2f}" '
            f'fill="{color}" {transform}/>'
        )
    if kind == "square":
        return (
            f'<rect x="{x - size:.2f}" y="{y - size:.2f}" '
            f'width="{2 * size:.2f}" height="{2 * size:.2f}" '
            f'fill="{color}" {transform}/>'
        )
    if kind == "triangle":
        pts = []
        for i in range(3):
            ang = math.radians(-90 + i * 120)
            px = x + size * math.cos(ang)
            py = y + size * math.sin(ang)
            pts.append(f"{px:.2f},{py:.2f}")
        return (
            f'<polygon points="{" ".join(pts)}" fill="{color}" {transform}/>'
        )
    if kind == "star":
        pts = []
        for i in range(10):
            r = size if i % 2 == 0 else size * 0.45
            ang = math.radians(-90 + i * 36)
            px = x + r * math.cos(ang)
            py = y + r * math.sin(ang)
            pts.append(f"{px:.2f},{py:.2f}")
        return (
            f'<polygon points="{" ".join(pts)}" fill="{color}" {transform}/>'
        )
    raise ValueError(f"未知形状: {kind}")


SHAPES = ("circle", "square", "triangle", "star")


# ──────────────────────────────────────────────────────────────
# 拼装 SVG
# ──────────────────────────────────────────────────────────────

def wrap_svg(
    width: int, height: int, body: str, *, background: str | None = None
) -> str:
    """拼装最终 SVG 文档。

    可选 ``background`` 参数为底层背景 SVG（嵌套）。
    """
    bg = ""
    if background:
        # 把背景 SVG 当作 image 嵌入（保持隔离）
        import base64

        b64 = base64.b64encode(background.encode("utf-8")).decode("ascii")
        bg = (
            f'<image x="0" y="0" width="{width}" height="{height}" '
            f'href="data:image/svg+xml;base64,{b64}"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        f'{bg}{body}</svg>'
    )


def to_data_uri(svg: str) -> str:
    """将 SVG 字符串转为 data URI，便于 ``<img src>`` 使用。"""
    import base64

    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"
