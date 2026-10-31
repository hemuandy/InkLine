"""生成 README 用的示意图（风格总览 / 前后对比）。"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inkline.core.analyzer import analyze, auto_params
from inkline.core.params import METHODS, METHOD_LABELS, Params
from inkline.core.renderer import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "screenshots")

FONT_PATHS = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]

BG = (20, 22, 26)
INK = (236, 236, 236)
ACCENT = (217, 86, 74)


def font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def to_pil(bgr: np.ndarray) -> Image.Image:
    if bgr.ndim == 2:
        return Image.fromarray(bgr)
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def load(path: str) -> np.ndarray:
    from inkline.imageio import load_image
    return load_image(path)


def style_grid() -> None:
    """一张图 × 六种风格（第一格放原图）。"""
    src_path = os.path.join(ROOT, "_samples", "portrait.jpg")
    if not os.path.exists(src_path):
        print("缺少样本图，跳过风格总览")
        return
    img = load(src_path)
    info = analyze(img)
    smart = auto_params(info)

    cells = [("原图", img)]
    for key, _name, _hint in METHODS:
        if key == "smart":
            continue
        res = render(img, smart if key == "line" else Params(method=key), max_side=640)
        cells.append((METHOD_LABELS[key], res.image))

    cell_w, cell_h, pad, top = 420, 560, 16, 44
    cols, rows = 3, 2
    width = cols * cell_w + pad * (cols + 1)
    height = rows * (cell_h + top) + pad * (rows + 1)
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)
    title_font = font(22)

    for idx, (label, im) in enumerate(cells[: cols * rows]):
        col, row = idx % cols, idx // cols
        x = pad + col * (cell_w + pad)
        y = pad + row * (cell_h + top + pad) + top
        draw.text((x, y - top + 8), label, font=title_font, fill=ACCENT if idx else INK)
        pic = to_pil(im)
        ratio = min(cell_w / pic.width, cell_h / pic.height)
        pic = pic.resize((int(pic.width * ratio), int(pic.height * ratio)), Image.LANCZOS)
        ox = x + (cell_w - pic.width) // 2
        oy = y + (cell_h - pic.height) // 2
        canvas.paste(pic, (ox, oy))

    path = os.path.join(OUT, "styles.png")
    canvas.save(path)
    print("wrote", path)


def before_after() -> None:
    src_path = os.path.join(ROOT, "_samples", "portrait.jpg")
    if not os.path.exists(src_path):
        return
    img = load(src_path)
    res = render(img, auto_params(analyze(img)), max_side=640)
    left = to_pil(img).convert("RGB")
    right = to_pil(res.image).convert("RGB")
    h = 560
    left = left.resize((int(left.width * h / left.height), h), Image.LANCZOS)
    right = right.resize((int(right.width * h / right.height), h), Image.LANCZOS)
    gap, pad, top = 14, 18, 46
    width = left.width + right.width + gap + pad * 2
    canvas = Image.new("RGB", (width, h + top + pad), BG)
    canvas.paste(left, (pad, top))
    canvas.paste(right, (pad + left.width + gap, top))
    draw = ImageDraw.Draw(canvas)
    f = font(20)
    draw.text((pad, 14), "原图", font=f, fill=INK)
    draw.text((pad + left.width + gap, 14), "墨线 · 智能模式", font=f, fill=ACCENT)
    path = os.path.join(OUT, "before_after.png")
    canvas.save(path)
    print("wrote", path)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    style_grid()
    before_after()


if __name__ == "__main__":
    main()
