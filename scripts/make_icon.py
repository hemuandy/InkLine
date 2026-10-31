"""生成应用图标：墨色圆角底 + 一笔白色书法线 + 朱砂印。"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(HERE, "inkline", "assets")

SIZE = 1024
BG = (20, 22, 26, 255)
INK = (245, 246, 248, 255)
SEAL = (217, 86, 74, 255)


def bezier(points, t):
    p = np.array(points, dtype=float)
    while len(p) > 1:
        p = (1 - t) * p[:-1] + t * p[1:]
    return p[0]


def stroke(draw, points, width_start, width_end, color, samples=260):
    pts = [tuple(bezier(points, i / (samples - 1))) for i in range(samples)]
    left, right = [], []
    for i, (x, y) in enumerate(pts):
        if i == 0:
            dx, dy = pts[1][0] - x, pts[1][1] - y
        elif i == samples - 1:
            dx, dy = x - pts[-2][0], y - pts[-2][1]
        else:
            dx, dy = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        length = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        nx, ny = -dy / length, dx / length
        t = i / (samples - 1)
        w = (width_start * (1 - t) ** 1.6 + width_end * t ** 0.7) / 2
        # 首尾收锋
        taper = min(1.0, (0.5 + 0.5 * min(t * 12, 1)) * (0.35 + 0.65 * min((1 - t) * 8, 1)) ** 0.4)
        w *= taper
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    draw.polygon(left + right[::-1], fill=color)
    r = max(2, width_start * 0.10)
    draw.ellipse([pts[0][0] - r, pts[0][1] - r, pts[0][0] + r, pts[0][1] + r], fill=color)


def main():
    os.makedirs(ASSETS, exist_ok=True)
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=232, fill=BG,
                        outline=(44, 49, 59, 255), width=8)

    # 主笔：从左上扫到右下，带一个转折
    stroke(d, [(232, 700), (330, 300), (660, 690), (812, 300)],
           width_start=118, width_end=34, color=INK)

    # 朱砂印
    seal = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(seal)
    sd.ellipse([700, 690, 880, 870], fill=SEAL)
    seal = seal.filter(ImageFilter.GaussianBlur(1.2))
    img = Image.alpha_composite(img, seal)

    img.save(os.path.join(ASSETS, "icon.png"), format="PNG")
    img.resize((512, 512), Image.LANCZOS).save(os.path.join(ASSETS, "icon_512.png"))
    img.save(os.path.join(ASSETS, "icon.ico"), format="ICO",
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written to", ASSETS)


if __name__ == "__main__":
    main()
